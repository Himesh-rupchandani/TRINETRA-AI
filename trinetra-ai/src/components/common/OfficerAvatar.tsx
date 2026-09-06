import { useState } from 'react';
import { UserRound } from 'lucide-react';
import type { OfficerProfile } from '@/types';
import { cn } from '@/lib/utils';
import { useCurrentOfficer } from '@/hooks/useCurrentOfficer';

/**
 * An officer's photo in a circular tile. With no `officer` prop it shows the
 * active officer, so the sidebar, header and Profile page always match.
 * Falls back to the generic avatar icon while loading or if the photo 404s.
 */
export function OfficerAvatar({
  officer,
  size = 36,
  className,
}: {
  officer?: OfficerProfile | null;
  size?: number;
  className?: string;
}) {
  const active = useCurrentOfficer();
  const subject = officer ?? active;
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const photo = subject?.photoUrl && subject.photoUrl !== failedSrc ? subject.photoUrl : undefined;

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
        <img
          src={photo}
          alt=""
          className="h-full w-full object-cover object-top"
          onError={() => setFailedSrc(photo)}
        />
      ) : (
        <UserRound size={Math.round(size * 0.45)} />
      )}
    </span>
  );
}
