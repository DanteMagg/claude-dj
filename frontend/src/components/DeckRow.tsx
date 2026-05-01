import DeckPanel from './DeckPanel';
import type { DjDeck, DjDeckB, LibraryTrack } from '../types';

interface Props {
  deckA:      DjDeck | null;
  deckB:      DjDeckB | null;
  reasoning:  string;
  trackByHash:  (hash: string) => LibraryTrack | undefined;
  trackByTitle: (title: string) => LibraryTrack | undefined;
}

export default function DeckRow({ deckA, deckB, reasoning, trackByHash, trackByTitle }: Props) {
  const trackA = deckA ? trackByHash(deckA.hash) : undefined;
  // Prefer hash lookup (reliable); fall back to title only if hash not yet set
  const trackB = deckB
    ? (deckB.hash ? trackByHash(deckB.hash) : trackByTitle(deckB.title))
    : undefined;

  return (
    <div style={{
      display: 'flex',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      overflow: 'hidden',
    }}>
      <DeckPanel variant="a" deck={deckA} track={trackA} reasoning="" />
      <DeckPanel variant="b" deck={deckB} track={trackB} reasoning={reasoning} />
    </div>
  );
}
