import { EntraApp } from './App.entra';
import { MockAuthApp } from './App.mock';

// AUTH_MODE switch: "entra" (default/unset) renders the original, unmodified MSAL app shell
// (App.entra.tsx). "mock" is an additive local-dev branch (App.mock.tsx) used while the
// deployment's service principal has no Entra ID app-registration permissions yet. Unsetting
// VITE_AUTH_MODE (or setting it to "entra") restores the original app with no other changes.
const authMode = import.meta.env.VITE_AUTH_MODE ?? 'entra';

function App() {
  return authMode === 'mock' ? <MockAuthApp /> : <EntraApp />;
}

export default App;
