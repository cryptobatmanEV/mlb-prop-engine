import { createHmac, timingSafeEqual } from 'crypto';

export type IframeIdentity = {
  discordId:       string;
  discordUsername: string;
};

// theevcave.com has already authenticated the user via Discord OAuth, so
// discord_id/discord_user are trusted as-is. If a signed token is also
// present (HMAC-SHA256 of `discord_id:discord_user` under IFRAME_SECRET), it
// must match — this guards against a forged token, but a missing token does
// not block the request.
export function verifyIframeIdentity(
  discordId: string | null,
  discordUser: string | null,
  token: string | null,
): IframeIdentity | null {
  if (!discordId || !discordUser) return null;

  const secret = process.env.IFRAME_SECRET;
  if (secret && token) {
    const expected = createHmac('sha256', secret).update(`${discordId}:${discordUser}`).digest('hex');
    const expectedBuf = Buffer.from(expected);
    const tokenBuf    = Buffer.from(token);
    if (expectedBuf.length !== tokenBuf.length || !timingSafeEqual(expectedBuf, tokenBuf)) return null;
  }

  return { discordId, discordUsername: discordUser };
}

// Reads and verifies the identity headers a request sends (see
// app/lib/iframeIdentity.ts on the client for how these are set).
export function getVerifiedIdentity(req: Request): IframeIdentity | null {
  return verifyIframeIdentity(
    req.headers.get('x-discord-id'),
    req.headers.get('x-discord-user'),
    req.headers.get('x-discord-token'),
  );
}
