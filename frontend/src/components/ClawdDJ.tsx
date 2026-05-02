import type { PlayerState } from "../hooks/usePlayer";

export default function ClawdDJ({ state, size = 60 }: { state: PlayerState; size?: number }) {
  const playing   = state === "playing";
  const buffering = state === "buffering";
  const err       = state === "error";
  const accent    = err ? "#ff375f" : "#ff5f00";

  return (
    <>
      <div
        className={`cdj${playing ? " cdj--play" : ""}${buffering ? " cdj--buf" : ""}`}
        style={{ width: size, height: size, flexShrink: 0 }}
      >
        <svg viewBox="0 0 100 100" fill="none" style={{ overflow: "visible" }}>
          <defs>
            <filter id="cdj-glow" x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="2.5" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* headphone band shadow */}
          <path d="M26 54 C26 22 74 22 74 54" stroke="#000" strokeWidth="10" strokeLinecap="round" />
          {/* headphone band */}
          <path d="M26 54 C26 22 74 22 74 54"
            stroke="#1e1e1e" strokeWidth="7" strokeLinecap="round" />
          <path d="M26 54 C26 22 74 22 74 54"
            stroke={playing ? accent : "#2c2c2c"} strokeWidth="2.5"
            strokeLinecap="round" className="cdj-band" />

          {/* head */}
          <circle cx="50" cy="59" r="31" fill="#0e0e0e" />
          <circle cx="50" cy="59" r="31"
            stroke={accent} strokeWidth="1.5"
            opacity={playing ? 0.85 : 0.2} />

          {/* left cup */}
          <circle cx="22" cy="56" r="13" fill="#131313" stroke={playing ? accent : "#1c1c1c"} strokeWidth="1.5" />
          <circle cx="22" cy="56" r="6"  fill={playing ? "#ff5f0025" : "#0a0a0a"} />
          <circle cx="22" cy="56" r="2.5" fill={accent} opacity={playing ? 1 : 0.25} className="cdj-dot" />

          {/* right cup */}
          <circle cx="78" cy="56" r="13" fill="#131313" stroke={playing ? accent : "#1c1c1c"} strokeWidth="1.5" />
          <circle cx="78" cy="56" r="6"  fill={playing ? "#ff5f0025" : "#0a0a0a"} />
          <circle cx="78" cy="56" r="2.5" fill={accent} opacity={playing ? 1 : 0.25} className="cdj-dot" />

          {/* eyes */}
          <circle cx="41" cy="55" r="6.5" fill={accent}
            className="cdj-eye" filter={playing ? "url(#cdj-glow)" : undefined} />
          <ellipse cx="42.8" cy="52.8" rx="2.2" ry="1.6" fill="white" opacity="0.42" />

          <circle cx="59" cy="55" r="6.5" fill={accent}
            className="cdj-eye cdj-eye-r" filter={playing ? "url(#cdj-glow)" : undefined} />
          <ellipse cx="60.8" cy="52.8" rx="2.2" ry="1.6" fill="white" opacity="0.42" />

          {/* waveform mouth — 6 bars anchored at y=75 */}
          <rect className="cdj-bar b1" x="33" y="69" width="4" height="6"  rx="2" fill={accent} />
          <rect className="cdj-bar b2" x="40" y="66" width="4" height="9"  rx="2" fill={accent} />
          <rect className="cdj-bar b3" x="47" y="68" width="4" height="7"  rx="2" fill={accent} />
          <rect className="cdj-bar b4" x="54" y="65" width="4" height="10" rx="2" fill={accent} />
          <rect className="cdj-bar b5" x="61" y="69" width="4" height="6"  rx="2" fill={accent} />
          <rect className="cdj-bar b6" x="68" y="66" width="4" height="9"  rx="2" fill={accent} />
        </svg>
      </div>

      <style>{`
        .cdj { position: relative; }
        .cdj--play { animation: cdj-bob 750ms ease-in-out infinite alternate; }
        .cdj--buf  { animation: cdj-breathe 1.1s ease-in-out infinite; }

        @keyframes cdj-bob     { from{transform:translateY(0)} to{transform:translateY(-6px)} }
        @keyframes cdj-breathe { 0%,100%{opacity:1} 50%{opacity:.4} }

        .cdj-eye {
          transform-box: fill-box; transform-origin: center;
          animation: cdj-blink 5.5s ease-in-out infinite;
        }
        .cdj-eye-r { animation-delay: 130ms; }
        @keyframes cdj-blink { 0%,84%,100%{transform:scaleY(1)} 88%{transform:scaleY(0.06)} }

        .cdj-dot { transform-box:fill-box; transform-origin:center; }
        .cdj--play .cdj-dot { animation: cdj-dot-beat 750ms ease-in-out infinite alternate; }
        @keyframes cdj-dot-beat { from{transform:scale(1)} to{transform:scale(1.8)} }

        .cdj-band { }
        .cdj--play .cdj-band { animation: cdj-band-fade 2s ease-in-out infinite; }
        @keyframes cdj-band-fade { 0%,100%{opacity:1} 50%{opacity:.3} }

        .cdj-bar { transform-box:fill-box; transform-origin:bottom center; }
        .cdj:not(.cdj--play) .cdj-bar { transform:scaleY(0.22); transition:transform .4s ease; }

        .cdj--play .b1 { animation: cdj-b1 520ms ease-in-out infinite alternate; }
        .cdj--play .b2 { animation: cdj-b2 370ms ease-in-out infinite alternate; }
        .cdj--play .b3 { animation: cdj-b3 620ms ease-in-out infinite alternate; }
        .cdj--play .b4 { animation: cdj-b4 450ms ease-in-out infinite alternate; }
        .cdj--play .b5 { animation: cdj-b5 560ms ease-in-out infinite alternate; }
        .cdj--play .b6 { animation: cdj-b6 410ms ease-in-out infinite alternate; }

        @keyframes cdj-b1{from{transform:scaleY(.25)}to{transform:scaleY(1.05)}}
        @keyframes cdj-b2{from{transform:scaleY(.5)} to{transform:scaleY(1.55)}}
        @keyframes cdj-b3{from{transform:scaleY(.2)} to{transform:scaleY(.95)}}
        @keyframes cdj-b4{from{transform:scaleY(.6)} to{transform:scaleY(1.65)}}
        @keyframes cdj-b5{from{transform:scaleY(.3)} to{transform:scaleY(1.1)}}
        @keyframes cdj-b6{from{transform:scaleY(.45)}to{transform:scaleY(1.4)}}
      `}</style>
    </>
  );
}
