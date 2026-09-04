using System.Net;
using Microsoft.Azure.Cosmos;
using Microsoft.Azure.Cosmos.Linq;

namespace WebApp.Api.Services;

/// <summary>
/// Per-user conversation metadata (id, title, owner, timestamps) — not chat message content,
/// which stays in Foundry's own Conversations API. Foundry's conversation store is agent-scoped,
/// not user-scoped, so this is what makes "my conversations" possible once there's more than one
/// user. See infra/terraform/main.tf (azurerm_cosmosdb_*) for the provisioned resources.
/// </summary>
public record ConversationRecord
{
    public required string Id { get; init; }
    public required string UserId { get; init; }
    public string Title { get; init; } = "New conversation";
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset UpdatedAt { get; init; }
    public bool Deleted { get; init; }
}

public class ConversationStore
{
    private readonly Container _container;
    private readonly ILogger<ConversationStore> _logger;

    public ConversationStore(IConfiguration configuration, ILogger<ConversationStore> logger)
    {
        _logger = logger;

        var endpoint = configuration["COSMOS_ENDPOINT"]
            ?? throw new InvalidOperationException("COSMOS_ENDPOINT is not configured");
        var databaseName = configuration["COSMOS_DATABASE"]
            ?? throw new InvalidOperationException("COSMOS_DATABASE is not configured");
        var containerName = configuration["COSMOS_CONVERSATIONS_CONTAINER"]
            ?? throw new InvalidOperationException("COSMOS_CONVERSATIONS_CONTAINER is not configured");

        var credential = AzureCredentialResolver.Resolve(configuration, logger);
        var client = new CosmosClient(endpoint, credential, new CosmosClientOptions
        {
            SerializerOptions = new CosmosSerializationOptions
            {
                PropertyNamingPolicy = CosmosPropertyNamingPolicy.CamelCase,
            },
        });
        _container = client.GetContainer(databaseName, containerName);
    }

    public async Task RegisterAsync(string conversationId, string userId, string title, CancellationToken cancellationToken)
    {
        var record = new ConversationRecord
        {
            Id = conversationId,
            UserId = userId,
            Title = title,
            CreatedAt = DateTimeOffset.UtcNow,
            UpdatedAt = DateTimeOffset.UtcNow,
        };
        await _container.UpsertItemAsync(record, new PartitionKey(userId), cancellationToken: cancellationToken);
        _logger.LogInformation("Registered conversation {ConversationId} for user {UserId}", conversationId, userId);
    }

    /// <summary>Returns up to <paramref name="limit"/> + 1 records (the extra one signals "more exist").</summary>
    public async Task<List<ConversationRecord>> ListAsync(string userId, int limit, CancellationToken cancellationToken)
    {
        var fetchLimit = limit + 1;
        var query = _container.GetItemLinqQueryable<ConversationRecord>(
                requestOptions: new QueryRequestOptions { PartitionKey = new PartitionKey(userId) })
            .Where(c => c.UserId == userId && !c.Deleted)
            .OrderByDescending(c => c.UpdatedAt)
            .Take(fetchLimit);

        var results = new List<ConversationRecord>();
        using var iterator = query.ToFeedIterator();
        while (iterator.HasMoreResults)
        {
            var page = await iterator.ReadNextAsync(cancellationToken);
            results.AddRange(page);
        }
        return results;
    }

    /// <summary>Returns null if the conversation doesn't exist, isn't owned by <paramref name="userId"/>, or is soft-deleted.</summary>
    public async Task<ConversationRecord?> GetAsync(string conversationId, string userId, CancellationToken cancellationToken)
    {
        try
        {
            var response = await _container.ReadItemAsync<ConversationRecord>(
                conversationId, new PartitionKey(userId), cancellationToken: cancellationToken);
            return response.Resource.Deleted ? null : response.Resource;
        }
        catch (CosmosException ex) when (ex.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }
    }

    public async Task<bool> SoftDeleteAsync(string conversationId, string userId, CancellationToken cancellationToken)
    {
        var existing = await GetAsync(conversationId, userId, cancellationToken);
        if (existing is null)
        {
            return false;
        }

        var updated = existing with { Deleted = true, UpdatedAt = DateTimeOffset.UtcNow };
        await _container.UpsertItemAsync(updated, new PartitionKey(userId), cancellationToken: cancellationToken);
        _logger.LogInformation("Soft-deleted conversation {ConversationId} for user {UserId}", conversationId, userId);
        return true;
    }
}
