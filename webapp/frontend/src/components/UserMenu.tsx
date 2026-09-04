import React from 'react';
import { Avatar, Button, Text, makeStyles, tokens } from '@fluentui/react-components';
import { SignOut24Regular } from '@fluentui/react-icons';

interface UserMenuProps {
  displayName: string;
  onSignOut: () => void;
}

const useStyles = makeStyles({
  root: {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacingHorizontalS,
  },
  name: {
    flex: 1,
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
});

export const UserMenu: React.FC<UserMenuProps> = ({ displayName, onSignOut }) => {
  const styles = useStyles();

  return (
    <div className={styles.root}>
      <Avatar name={displayName} size={28} />
      <Text className={styles.name} weight="semibold" size={300}>
        {displayName}
      </Text>
      <Button
        appearance="subtle"
        icon={<SignOut24Regular />}
        size="small"
        aria-label="Sign out"
        onClick={onSignOut}
      />
    </div>
  );
};
