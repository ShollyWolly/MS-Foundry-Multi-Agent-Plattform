namespace WebApp.Api.Models;

// Request body for the AUTH_MODE=mock login endpoint. See Program.cs.
public record LoginRequest(string Username, string Password);
