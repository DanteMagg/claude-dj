import DeckPanel from './DeckPanel';
import type { DjDeck, DjDeckB, LibraryTrack } from '../types';

interface Props {
  deckA:      DjDeck | null;
  deckB:      DjDeckB | null;
  sessionId:  string | null;
  trackByHash:  (hash: string) => LibraryTrack | undefined;
  trackByTitle: (title: string) => LibraryTrack | undefined;
}

export default function DeckRow({ deckA, deckB, sessionId, trackByHash, trackByTitle }: Props) {
  const trackA = deckA ? trackByHash(deckA.hash) : undefined;
  // deck_b has no hash from the API — use title-based lookup as best-effort
  const trackB = deckB ? trackByTitle(deckB.title) : undefined;

  return (
    <div style={{
      display: 'flex',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      <DeckPanel variant="a" deck={deckA} sessionId={sessionId} track={trackA} />
      <DeckPanel variant="b" deck={deckB} sessionId={sessionId} track={trackB} />
    </div>
  );
}
