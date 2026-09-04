using Azure.Core;
using Azure.Identity;

namespace WebApp.Api.Services;

/// <summary>
/// Shared credential-selection logic for talking to Azure data planes (Foundry, Cosmos DB) —
/// extracted from AgentFrameworkService so ConversationStore doesn't duplicate it and drift.
/// </summary>
public static class AzureCredentialResolver
{
    public static TokenCredential Resolve(IConfiguration configuration, ILogger logger, string? managedIdentityClientId = null)
    {
        var environment = configuration["ASPNETCORE_ENVIRONMENT"] ?? "Production";

        // Local Docker mock-auth stack: when a service principal secret is supplied via env vars
        // (AZURE_CLIENT_ID/AZURE_CLIENT_SECRET/AZURE_TENANT_ID), prefer it over the
        // Development/Production branches below — those require az/azd CLI login or managed
        // identity, neither of which exist inside a plain container. This branch is additive and
        // inert whenever AZURE_CLIENT_SECRET is unset (e.g. real Azure Container Apps deployments),
        // so the original credential chain below is unchanged and still the default.
        if (!string.IsNullOrEmpty(configuration["AZURE_CLIENT_SECRET"]))
        {
            logger.LogInformation("Local Docker: Using EnvironmentCredential (service principal from env vars)");
            return new EnvironmentCredential();
        }

        if (environment == "Development")
        {
            logger.LogInformation("Development: Using ChainedTokenCredential (AzureCli -> AzureDeveloperCli)");
            return new ChainedTokenCredential(
                new AzureCliCredential(),
                new AzureDeveloperCliCredential()
            );
        }

        if (!string.IsNullOrEmpty(managedIdentityClientId))
        {
            logger.LogInformation("Production: Using user-assigned ManagedIdentityCredential: {MiClientId}", managedIdentityClientId);
            return new ManagedIdentityCredential(ManagedIdentityId.FromUserAssignedClientId(managedIdentityClientId));
        }

        logger.LogInformation("Production: Using ManagedIdentityCredential (system-assigned)");
        return new ManagedIdentityCredential(ManagedIdentityId.SystemAssigned);
    }
}
