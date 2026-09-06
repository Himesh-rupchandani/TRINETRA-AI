import { useState } from 'react';
import { UserRound } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCurrentOfficer } from '@/hooks/useCurrentOfficer';

/**
 * The signed-in officer's photo, used by both System Operator profile areas
 * (sidebar + header) so they always show the same image as the Profile page.
 * Falls back to the generic avatar icon while loading or if the photo 404s.
 */
export function OfficerAvatar({ size = 36, className }: { size?: number; className?: string }) {
  const officer = useCurrentOfficer();
  const [failed, setFailed] = useState(false);
  const photo = !failed ? officer?.photoUrl : undefined;

  return (
    <span
      className={cn(
        'grid shrink-0 place-items-center overflow-hidden rounded-full bg-brand/10 text-brand ring-1 ring-line',
        className,
      )}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {photo ? (
        <img src={photo} alt="" className="h-full w-full object-cover object-top" onError={() => setFailed(true)} />
      ) : (
        <UserRound size={Math.round(size * 0.45)} />
      )}
    </span>
  );
}
