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
    const search      = window.location.search;
    const params      = new URLSearchParams(search);
    const discordId   = params.get('discord_id');
    const discordUser = params.get('discord_user');
    const token       = params.get('token');

    // eslint-disable-next-line no-console
    console.log('[iframeIdentity] location.search =', search);
    // eslint-disable-next-line no-console
    console.log('[iframeIdentity] parsed params: discord_id =', discordId, ', discord_user =', discordUser, ', token =', token ? `${token.slice(0, 6)}... (len ${token.length})` : token);

    if (discordId && discordUser && token) {
      const value: IframeIdentity = { discordId, discordUser, token };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
        // eslint-disable-next-line no-console
        console.log('[iframeIdentity] all 3 URL params present, cached to localStorage, identity =', { discordId, discordUser });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('[iframeIdentity] localStorage.setItem failed (storage blocked?) — using identity for this load only:', e);
      }
      setIdentity(value);
      return;
    }

    if (discordId || discordUser || token) {
      // eslint-disable-next-line no-console
      console.warn('[iframeIdentity] incomplete identity params in URL — discord_id, discord_user, and token must ALL be present. Got:', { discordId, discordUser, hasToken: !!token });
    }

    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line no-console
      console.log('[iframeIdentity] no complete URL params, checked localStorage, found =', stored ? 'cached identity' : 'nothing');
      setIdentity(stored ? (JSON.parse(stored) as IframeIdentity) : null);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('[iframeIdentity] localStorage.getItem failed (storage blocked in this iframe context?):', e);
      setIdentity(null);
    }
  }, []);

  return identity;
}

// True if the URL has discord_id/discord_user but is missing (or has an
// empty) token — i.e. theevcave.com identified the user but the HMAC token
// needed to verify that identity server-side wasn't included. Used to show a
// more specific message than a generic "sign in" prompt.
export function hasIncompleteUrlIdentity(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  const discordId   = params.get('discord_id');
  const discordUser = params.get('discord_user');
  const token       = params.get('token');
  return !!(discordId && discordUser) && !token;
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
