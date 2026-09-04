import { Button, Field, Input, Spinner, Text } from '@fluentui/react-components';
import { useCallback, useEffect, useState } from 'react';
import { ErrorBoundary } from './components/core/ErrorBoundary';
import { AgentChat } from './components/AgentChat';
import type { IAgentMetadata } from './types/chat';
import './App.css';

const apiUrl = import.meta.env.VITE_API_URL || '/api';

// Additive local-dev auth shell, used only when VITE_AUTH_MODE=mock (see App.tsx). Talks to the
// backend's AUTH_MODE=mock endpoints (Program.cs: /api/auth/login, /me) instead of MSAL/Entra ID.
// This file can be deleted along with the AUTH_MODE switch to fully revert to Entra-only auth.
export function MockAuthApp() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null); // null = still checking session
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [agentMetadata, setAgentMetadata] = useState<IAgentMetadata | null>(null);
  const [isLoadingAgent, setIsLoadingAgent] = useState(false);

  // Check for an existing mock session (e.g. after a page refresh) on mount.
  useEffect(() => {
    fetch(`${apiUrl}/auth/me`, { credentials: 'include' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          setUsername(data.username ?? '');
        }
        setLoggedIn(res.ok);
      })
      .catch(() => setLoggedIn(false));
  }, []);

  const fetchAgentMetadata = useCallback(async () => {
    setIsLoadingAgent(true);
    try {
      const response = await fetch(`${apiUrl}/agent`, { credentials: 'include' });
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      setAgentMetadata(data);
      document.title = data.name ? `${data.name} - Azure AI Agent` : 'Azure AI Agent';
    } catch (error) {
      console.error('Error fetching agent metadata:', error);
      setAgentMetadata({
        id: 'fallback-agent',
        object: 'agent',
        createdAt: Date.now() / 1000,
        name: 'Azure AI Agent',
        description: 'Your intelligent conversational partner powered by Azure AI',
        model: 'gpt-4o-mini',
        metadata: { logo: 'Avatar_Default.svg' },
      });
      document.title = 'Azure AI Agent';
    } finally {
      setIsLoadingAgent(false);
    }
  }, []);

  useEffect(() => {
    if (loggedIn) fetchAgentMetadata();
  }, [loggedIn, fetchAgentMetadata]);

  const handleLogin = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setIsSubmitting(true);
      setLoginError(null);
      try {
        const response = await fetch(`${apiUrl}/auth/login`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password }),
        });
        if (!response.ok) {
          setLoginError('Invalid username or password.');
          setLoggedIn(false);
          return;
        }
        setLoggedIn(true);
      } catch {
        setLoginError('Could not reach the server. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
    },
    [username, password]
  );

  const handleSignOut = useCallback(async () => {
    try {
      await fetch(`${apiUrl}/auth/logout`, { method: 'POST', credentials: 'include' });
    } catch {
      // best-effort — still drop the local session below regardless
    }
    setLoggedIn(false);
    setUsername('');
    setPassword('');
    setAgentMetadata(null);
  }, []);

  const centered = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    flexDirection: 'column' as const,
    gap: '1rem',
  };

  if (loggedIn === null) {
    return (
      <div className="app-container" style={centered}>
        <Spinner size="large" />
        <p style={{ margin: 0 }}>Preparing your session...</p>
      </div>
    );
  }

  if (!loggedIn) {
    return (
      <div className="app-container" style={centered}>
        <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', width: '280px' }}>
          <Text weight="semibold" size={500}>Sign in</Text>
          <Field label="Username">
            <Input value={username} onChange={(_, data) => setUsername(data.value)} autoFocus />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} onChange={(_, data) => setPassword(data.value)} />
          </Field>
          {loginError && <Text style={{ color: 'var(--colorPaletteRedForeground1, crimson)' }}>{loginError}</Text>}
          <Button appearance="primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in...' : 'Sign in'}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      {isLoadingAgent || !agentMetadata ? (
        <div className="app-container" style={centered}>
          <Spinner size="large" />
          <p style={{ margin: 0 }}>Loading agent...</p>
        </div>
      ) : (
        <div className="app-container">
          <AgentChat
            agentId={agentMetadata.id}
            agentName={agentMetadata.name}
            agentDescription={agentMetadata.description || undefined}
            agentLogo={agentMetadata.metadata?.logo}
            starterPrompts={agentMetadata.starterPrompts || undefined}
            userDisplayName={username}
            onSignOut={handleSignOut}
          />
        </div>
      )}
    </ErrorBoundary>
  );
}
