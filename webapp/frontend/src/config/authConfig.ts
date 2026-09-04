import type { Configuration } from "@azure/msal-browser";
import { LogLevel } from "@azure/msal-browser";

// AUTH_MODE=mock (additive local-dev branch, see App.tsx/App.mock.tsx) never triggers an MSAL
// login, but msalConfig below is still constructed (MsalProvider stays mounted so useAuth()'s
// useMsal() call has a context). A placeholder GUID lets PublicClientApplication construct
// without throwing; MSAL makes no network call until a login is actually attempted, which the
// mock branch never does. This fallback is inert whenever VITE_AUTH_MODE isn't "mock".
const authMode = import.meta.env.VITE_AUTH_MODE ?? "entra";
const placeholderId = "00000000-0000-0000-0000-000000000000";

// Environment variables (must be set during build or deployment)
const clientId = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID || (authMode === "mock" ? placeholderId : undefined);

if (!clientId) {
  throw new Error(
    "VITE_ENTRA_SPA_CLIENT_ID is not set. This must be provided during build time. " +
    "For local dev, ensure azd environment is configured and run preprovision hook."
  );
}

// When OBO is enabled, scopes target the backend API app instead of the SPA
const scopeClientId = import.meta.env.VITE_ENTRA_BACKEND_CLIENT_ID || clientId;

const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID || (authMode === "mock" ? placeholderId : undefined);

if (!tenantId) {
  throw new Error(
    "VITE_ENTRA_TENANT_ID is not set. This must be provided during build time. " +
    "For local dev, run setup-local-dev.ps1 to configure from azd environment."
  );
}

export const msalConfig: Configuration = {
  auth: {
    clientId: clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: window.location.origin, // Will be https://<container-app-url> in production
    postLogoutRedirectUri: window.location.origin,
    navigateToLoginRequestUrl: false, // Avoid redirect loops
  },
  cache: {
    cacheLocation: "localStorage", // Use localStorage for token caching
    storeAuthStateInCookie: false, // Set to true if IE11 support needed
  },
  system: {
    loggerOptions: {
      logLevel: import.meta.env.DEV ? LogLevel.Info : LogLevel.Warning,
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        switch (level) {
          case LogLevel.Error:
            console.error(message);
            break;
          case LogLevel.Warning:
            console.warn(message);
            break;
          case LogLevel.Info:
            console.info(message);
            break;
          case LogLevel.Verbose:
            console.debug(message);
            break;
        }
      },
    },
  },
};

// API permission scope (will match app registration in Step 08)
export const loginRequest = {
  scopes: [`api://${scopeClientId}/Chat.ReadWrite`],
};

export const tokenRequest = {
  scopes: [`api://${scopeClientId}/Chat.ReadWrite`],
  forceRefresh: false, // Use cached token if valid
};
