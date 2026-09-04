import { useMsal } from "@azure/msal-react";
import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { tokenRequest } from "../config/authConfig";
import { useCallback, useMemo } from "react";

/**
 * Authentication hook for MSAL-based authentication.
 * Provides token acquisition and authentication status.
 * 
 * @returns Object with getAccessToken function, authentication status, and user info
 * 
 * @example
 * ```tsx
 * function ProtectedComponent() {
 *   const { getAccessToken, isAuthenticated, user } = useAuth();
 *   
 *   useEffect(() => {
 *     const fetchData = async () => {
 *       const token = await getAccessToken();
 *       if (token) {
 *         // Make authenticated API call
 *       }
 *     };
 *     fetchData();
 *   }, [getAccessToken]);
 *   
 *   if (!isAuthenticated) return <div>Please sign in</div>;
 *   return <div>Welcome, {user?.name}</div>;
 * }
 * ```
 */
// AUTH_MODE switch: "entra" (default, unset) is the original MSAL flow below, untouched.
// "mock" is an additive local-dev branch for the Docker stack (see MockAuthApp.tsx) — the
// backend authenticates the mock session via a cookie, not a bearer token, so the token
// returned here is a placeholder the backend never validates. Unsetting VITE_AUTH_MODE (or
// setting it back to "entra") restores the original MSAL-only behavior with no other changes.
const isMockAuth = import.meta.env.VITE_AUTH_MODE === "mock";

export const useAuth = () => {
  const { instance, accounts } = useMsal();

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    if (isMockAuth) {
      return "mock-session";
    }

    if (accounts.length === 0) {
      return null;
    }

    const request = {
      ...tokenRequest,
      account: accounts[0],
    };

    try {
      // Try silent token acquisition first (uses cached token if valid)
      const response = await instance.acquireTokenSilent(request);
      return response.accessToken;
    } catch (error) {
      if (error instanceof InteractionRequiredAuthError) {
        // Fallback to interactive login if silent fails
        console.warn(
          "Silent token acquisition failed, prompting for interaction"
        );
        try {
          const response = await instance.acquireTokenPopup(request);
          return response.accessToken;
        } catch (popupError) {
          console.error("Popup login failed:", popupError);
          return null;
        }
      }
      console.error("Token acquisition error:", error);
      return null;
    }
  }, [instance, accounts]);

  // Memoize computed values
  const isAuthenticated = useMemo(
    () => (isMockAuth ? true : accounts.length > 0),
    [accounts.length]
  );

  const user = useMemo(
    () => accounts[0],
    [accounts]
  );

  return useMemo(
    () => ({
      getAccessToken,
      isAuthenticated,
      user,
    }),
    [getAccessToken, isAuthenticated, user]
  );
};
