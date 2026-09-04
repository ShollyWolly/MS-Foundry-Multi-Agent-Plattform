import type { ReactNode } from 'react';
import { Body1, Subtitle1 } from '@fluentui/react-components';
import { AgentIcon } from '../core/AgentIcon';
import styles from './StarterMessages.module.css';

interface IStarterMessageProps {
  agentName?: string;
  agentDescription?: string;
  agentLogo?: string;
  /**
   * Starter prompts from agent metadata.
   * If not provided, falls back to default prompts.
   * 
   * Configure in Microsoft Foundry portal under agent Configuration > Starter prompts.
   * Prompts are stored as newline-separated text in the "starterPrompts" metadata key.
   */
  starterPrompts?: string[];
  onPromptClick?: (prompt: string) => void;
}

export const StarterMessages = ({
  agentName,
  agentDescription,
  agentLogo,
  starterPrompts,
  onPromptClick,
}: IStarterMessageProps): ReactNode => {
  // Only show prompts configured on the agent in Microsoft Foundry — no generic defaults.
  const prompts = starterPrompts ?? [];

  return (
    <div className={styles.zeroprompt}>
      <div className={styles.content}>
        <AgentIcon
          alt={agentName ?? "Agent"}
          size="large"
          logoUrl={agentLogo}
        />
        <Subtitle1 className={styles.welcome}>
          {agentName ? `Hello! I'm ${agentName}` : "Hello! How can I help you today?"}
        </Subtitle1>
        {agentDescription && (
          <Body1 className={styles.caption}>{agentDescription}</Body1>
        )}
      </div>

      {onPromptClick && prompts.length > 0 && (
        <ul className={styles.promptList}>
          {prompts.map((prompt, index) => (
            <li key={`prompt-${index}`}>
              <button
                className={styles.promptCard}
                onClick={() => onPromptClick(prompt)}
                type="button"
                title={prompt}
              >
                <span className={styles.promptText}>{prompt}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
