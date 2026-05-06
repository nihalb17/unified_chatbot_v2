/* eslint-disable react-hooks/set-state-in-effect -- typewriter resets display when content changes */
import { useState, useEffect, useRef } from 'react';

/**
 * Word-by-word reveal when stream is true.
 * onAnimationComplete is optional: runs when the full text is shown (or immediately for non-stream if provided).
 */
export default function TypewriterMessage({ content, stream, onAnimationComplete }) {
  const isStream = Boolean(stream);
  const [displayedText, setDisplayedText] = useState('');
  const completeRef = useRef(false);

  useEffect(() => {
    completeRef.current = false;
  }, [content, isStream]);

  useEffect(() => {
    if (!isStream) {
      if (onAnimationComplete) {
        const t = window.setTimeout(() => {
          if (completeRef.current) return;
          completeRef.current = true;
          onAnimationComplete();
        }, 0);
        return () => window.clearTimeout(t);
      }
      return;
    }

    const words = (content || '').split(/\s+/).filter((w) => w.length > 0);
    if (words.length === 0) {
      setDisplayedText('');
      if (onAnimationComplete && !completeRef.current) {
        completeRef.current = true;
        onAnimationComplete();
      }
      return;
    }

    let i = 0;
    setDisplayedText('');
    const id = window.setInterval(() => {
      if (i < words.length) {
        const w = words[i];
        setDisplayedText((prev) => (prev ? `${prev} ${w}` : w));
        i++;
      } else {
        window.clearInterval(id);
        if (onAnimationComplete && !completeRef.current) {
          completeRef.current = true;
          onAnimationComplete();
        }
      }
    }, 70);
    return () => window.clearInterval(id);
  }, [content, isStream, onAnimationComplete]);

  if (!isStream) {
    return <p>{content}</p>;
  }
  return <p>{displayedText}</p>;
}
