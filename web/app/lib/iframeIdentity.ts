'use client';

import { useEffect, useState } from 'react';

export type IframeIdentity = {
  discordId:   string;
  discordUser: string;
  token:       string;
};

const STORAGE_KEY = 'evcave_discord_identity';

// theevcave.com appends ?discord_id=...&discord_user=...&token=... to the
// iframe src once per page load. We capture it here and cache it in
// localStorage so it survives client-side navigation (which drops the query
// string) within the same tab.
export function useIframeIdentity(): IframeIdentity | null | undefined {
  const [identity, setIdentity] = useState<IframeIdentity | null | undefined>(undefined);

  useEffect(() => {
    const params      = new URLSearchParams(window.location.search);
    const discordId   = params.get('discord_id');
    const discordUser = params.get('discord_user');
    const token       = params.get('token');

    if (discordId && discordUser && token) {
      const value: IframeIdentity = { discordId, discordUser, token };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      setIdentity(value);
      return;
    }

    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      setIdentity(stored ? (JSON.parse(stored) as IframeIdentity) : null);
    } catch {
      setIdentity(null);
    }
  }, []);

  return identity;
}

// Headers to attach to /api/* requests so the server can re-verify identity.
export function identityHeaders(identity: IframeIdentity | null | undefined): HeadersInit {
  if (!identity) return {};
  return {
    'X-Discord-Id':    identity.discordId,
    'X-Discord-User':  identity.discordUser,
    'X-Discord-Token': identity.token,
  };
}
