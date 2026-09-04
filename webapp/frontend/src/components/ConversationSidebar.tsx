import React, { useCallback, useState, useRef, useMemo, useEffect } from 'react';
import {
  Button,
  Spinner,
  Text,
  Input,
  makeStyles,
  tokens,
} from '@fluentui/react-components';
import {
  PanelLeftContract24Regular,
  ChatAdd24Regular,
  Delete24Regular,
  Search24Regular,
  DismissCircle24Regular,
} from '@fluentui/react-icons';
import type { ConversationSummary } from '../types/appState';

interface ConversationSidebarProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  conversations: ConversationSummary[];
  isLoading: boolean;
  hasMore: boolean;
  currentConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onLoadMore: () => void;
  /** Rendered pinned to the bottom of the sidebar, below the scrollable conversation list. */
  footer?: React.ReactNode;
}

const SIDEBAR_WIDTH = '260px';

// Persistent docked panel (ChatGPT-style), not a Fluent Drawer/modal overlay — this is a
// permanent part of the page layout that pushes/reflows the chat area when toggled, rather than
// floating over it. See AgentChat.module.css's `.content` (flex row) for the layout side.
const useStyles = makeStyles({
  panel: {
    width: SIDEBAR_WIDTH,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    overflow: 'hidden',
    backgroundColor: tokens.colorNeutralBackground2,
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    transition: 'width 200ms ease, border-color 200ms ease',
  },
  panelCollapsed: {
    width: '0px',
    borderRightColor: 'transparent',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalM}`,
    flexShrink: 0,
  },
  body: {
    flex: 1,
    minHeight: 0,
    minWidth: 0,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: `0 ${tokens.spacingHorizontalM} ${tokens.spacingVerticalM}`,
    boxSizing: 'border-box',
  },
  newChatButton: {
    width: '100%',
    boxSizing: 'border-box',
    marginBottom: tokens.spacingVerticalM,
  },
  conversationList: {
    display: 'flex',
    flexDirection: 'column',
    gap: tokens.spacingVerticalXS,
  },
  conversationItem: {
    display: 'flex',
    alignItems: 'center',
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    cursor: 'pointer',
    border: 'none',
    backgroundColor: 'transparent',
    width: '100%',
    textAlign: 'left',
    gap: tokens.spacingHorizontalS,
    '&:hover': {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
  },
  conversationItemActive: {
    backgroundColor: tokens.colorNeutralBackground1Selected,
  },
  conversationContent: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  conversationTitle: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  conversationDate: {
    fontSize: tokens.fontSizeBase100,
    color: tokens.colorNeutralForeground3,
  },
  deleteButton: {
    flexShrink: 0,
    opacity: 0,
    '.conversation-item:hover &, .conversation-item:focus-within &': {
      opacity: 1,
    },
    ':focus': {
      opacity: 1,
    },
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: tokens.spacingVerticalXXL,
    color: tokens.colorNeutralForeground3,
    textAlign: 'center',
  },
  spinnerContainer: {
    display: 'flex',
    justifyContent: 'center',
    padding: tokens.spacingVerticalXXL,
  },
  loadMoreButton: {
    width: '100%',
    marginTop: tokens.spacingVerticalS,
  },
  searchBox: {
    width: '100%',
    boxSizing: 'border-box',
    marginBottom: tokens.spacingVerticalS,
  },
  noResults: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: tokens.spacingVerticalL,
    color: tokens.colorNeutralForeground3,
    textAlign: 'center',
  },
  footer: {
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalM}`,
    flexShrink: 0,
  },
});

function formatDate(timestamp: number): string {
  const date = new Date(timestamp * 1000); // Backend sends Unix seconds
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  isOpen,
  onOpenChange,
  conversations,
  isLoading,
  hasMore,
  currentConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onLoadMore,
  footer,
}) => {
  const styles = useStyles();
  const [searchQuery, setSearchQuery] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState('');

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleSearchChange = useCallback((_: React.ChangeEvent<HTMLInputElement>, data: { value: string }) => {
    setSearchQuery(data.value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(data.value);
    }, 300);
  }, []);

  const handleClearSearch = useCallback(() => {
    setSearchQuery('');
    setDebouncedQuery('');
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  const filteredConversations = useMemo(() => {
    if (!debouncedQuery.trim()) return conversations;
    const query = debouncedQuery.toLowerCase();
    return conversations.filter(c => c.title?.toLowerCase().includes(query));
  }, [conversations, debouncedQuery]);

  const handleDelete = useCallback(
    (e: React.MouseEvent, conversationId: string) => {
      e.stopPropagation();
      onDeleteConversation(conversationId);
    },
    [onDeleteConversation]
  );

  return (
    <div className={`${styles.panel} ${!isOpen ? styles.panelCollapsed : ''}`}>
      {isOpen && (
        <>
          <div className={styles.header}>
            <Text weight="semibold" size={400}>Conversations</Text>
            <Button
              appearance="subtle"
              aria-label="Collapse sidebar"
              icon={<PanelLeftContract24Regular />}
              onClick={() => onOpenChange(false)}
            />
          </div>

          <div className={styles.body}>
            <Button
              appearance="primary"
              icon={<ChatAdd24Regular />}
              className={styles.newChatButton}
              onClick={onNewChat}
            >
              New Chat
            </Button>

            {conversations.length > 0 && (
              <Input
                className={styles.searchBox}
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={handleSearchChange}
                contentBefore={<Search24Regular />}
                contentAfter={
                  searchQuery ? (
                    <Button
                      appearance="transparent"
                      icon={<DismissCircle24Regular />}
                      size="small"
                      aria-label="Clear search"
                      onClick={handleClearSearch}
                    />
                  ) : undefined
                }
                aria-label="Search conversations"
              />
            )}

            {isLoading && conversations.length === 0 ? (
              <div className={styles.spinnerContainer}>
                <Spinner size="small" label="Loading conversations..." />
              </div>
            ) : conversations.length === 0 ? (
              <div className={styles.emptyState}>
                <Text>No conversations yet</Text>
                <Text size={200}>Start a new chat to begin</Text>
              </div>
            ) : filteredConversations.length === 0 ? (
              <div className={styles.noResults}>
                <Text>No conversations match</Text>
                <Text size={200}>Try a different search term</Text>
              </div>
            ) : (
              <>
                <div className={styles.conversationList} role="list">
                  {filteredConversations.map((conversation) => (
                    <div
                      key={conversation.id}
                      className={`conversation-item ${styles.conversationItem} ${
                        conversation.id === currentConversationId
                          ? styles.conversationItemActive
                          : ''
                      }`}
                      role="listitem"
                      onClick={() => onSelectConversation(conversation.id)}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onSelectConversation(conversation.id);
                        }
                      }}
                    >
                      <div className={styles.conversationContent}>
                        <Text
                          weight="semibold"
                          size={300}
                          className={styles.conversationTitle}
                        >
                          {conversation.title || 'Untitled'}
                        </Text>
                        <Text className={styles.conversationDate}>
                          {formatDate(conversation.createdAt)}
                        </Text>
                      </div>
                      <Button
                        appearance="subtle"
                        icon={<Delete24Regular />}
                        size="small"
                        className={styles.deleteButton}
                        aria-label={`Delete conversation: ${conversation.title || 'Untitled'}`}
                        onClick={(e) => handleDelete(e, conversation.id)}
                      />
                    </div>
                  ))}
                </div>
                {hasMore && (
                  <Button
                    appearance="subtle"
                    className={styles.loadMoreButton}
                    onClick={onLoadMore}
                    disabled={isLoading}
                  >
                    {isLoading ? 'Loading...' : 'Load more conversations'}
                  </Button>
                )}
              </>
            )}
          </div>

          {footer && <div className={styles.footer}>{footer}</div>}
        </>
      )}
    </div>
  );
};
