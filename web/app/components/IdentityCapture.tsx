'use client';

import { useIframeIdentity } from '../lib/iframeIdentity';

// theevcave.com may land the iframe on any route with ?discord_id=...
// Mounting this in the root layout guarantees the identity gets captured
// into localStorage no matter which page receives the URL params, so it's
// available on /tracker (and everywhere else) after client-side navigation.
export default function IdentityCapture() {
  useIframeIdentity();
  return null;
}
