import { useAsync } from '@/hooks/useAsync';
import { apiUrl } from '@/services/api';
import { Shield, FileCheck, Hash, Lock, Download, Verified } from 'lucide-react';

interface Verification {
  status?: string;
  tampered?: boolean;
  findings?: string[];
  modified_fields?: { field: string; sealed: unknown; current: unknown }[];
  chain_integrity?: string;
  court_admissible?: boolean;
  evidence_hash?: string;
  previous_hash?: string;
  sealed_at?: string;
  seal_source?: string;
  verified_at?: string;
}

interface Certificate {
  certificate_id: string;
  evidence_details: { evidence_hash_sha256: string; plate_number: string; camera_id: string; timestamp: string; };
  certification: { certified_by: string; certified_at: string; digital_signature: string; case_number: string; };
  compliance: { bsa_2023_section_63: boolean; section_65b_indian_evidence_act: boolean; court_admissible: boolean };
  legal_statements: { bsa_2023_section_63: string; section_65b: string; tamper_proof: string };
}

export function EvidenceVault({ eventId }: { eventId: string | number }) {
  const cert = useAsync(async () => {
    const res = await fetch(apiUrl(`/reports/evidence/${eventId}/certificate`));
    if (!res.ok) throw new Error(`Certificate request responded ${res.status}`);
    return (await res.json()) as Certificate;
  }, [eventId]);

  // No invented verdict: when verification cannot be performed the panel says
  // UNVERIFIED instead of claiming VALID (which is what the old `catch` did —
  // an integrity claim nobody had checked).
  const verify = useAsync(async () => {
    const res = await fetch(apiUrl(`/reports/evidence/${eventId}/verify`));
    if (!res.ok) throw new Error(`verify responded ${res.status}`);
    return (await res.json()) as Verification;
  }, [eventId]);

  if (cert.loading) return <div className="panel p-4"><div className="skeleton h-40 w-full" /></div>;

  if (cert.error || !cert.data) {
    return (
      <div className="panel p-4 border-amber-200 bg-amber-50">
        <p className="text-xs font-bold text-amber-800">Evidence Certificate</p>
        <p className="mt-1 text-[11px] text-amber-700">Certificate generation requires GPS-tagged evidence with valid camera record. Demo/synthetic frames are marked as such and use separate evidence path. For production evidence, hash chain verification is available via <span className="font-mono">/api/reports/evidence/{'{id}'}/verify</span>{cert.error ? ` — backend error: ${cert.error}` : ''}.</p>
      </div>
    );
  }

  const c = cert.data;
  const v = verify.data ?? null;
  // The verdict comes from the backend's recomputation, never from a default.
  const verdict = v?.status ?? 'UNVERIFIED';
  const intact = verdict === 'VALID';
  const verdictTone = intact
    ? 'border-emerald-200 bg-emerald-600 text-white'
    : verdict === 'UNVERIFIED'
      ? 'border-slate-200 bg-slate-500 text-white'
      : 'border-red-200 bg-red-600 text-white';
  const admissible = v?.court_admissible ?? c.compliance?.court_admissible ?? false;

  return (
    <div className="panel overflow-hidden border-blue-200">
      <div className="panel-header bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white"><Shield size={18} /></div>
          <div>
            <h3 className="panel-title">Digital Evidence Certificate — BSA 2023 Compliant</h3>
            <p className="text-[11px] text-ink-faint">SHA256 • Chain of Custody • Tamper Detection • Court-Admissible • Section 65B</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`chip font-bold text-[10px] ${verdictTone}`}><Verified size={12} /> {verdict}</span>
          <span className="chip border-blue-200 bg-blue-600 text-white font-bold text-[10px]"><FileCheck size={12} /> BSA 2023 Sec 63</span>
        </div>
      </div>

      <div className="p-4 space-y-4">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2"><Hash size={14} className="text-ink-faint" /><span className="text-[11px] font-bold uppercase tracking-widest text-ink-faint">SHA256 Evidence Hash (Tamper-Proof)</span></div>
            <span
              className={`chip font-mono text-[10px] font-bold ${
                intact
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-red-200 bg-red-50 text-red-700'
              }`}
            >
              {verdict} • Chain {v?.chain_integrity ?? 'UNKNOWN'}
            </span>
          </div>
          <p className="mt-2 font-mono text-[11px] font-bold text-ink break-all leading-relaxed">{c.evidence_details?.evidence_hash_sha256 ?? '—'}</p>
          <p className="mt-2 text-[10px] leading-relaxed text-ink-faint">Hash computed from canonical JSON (event_id, camera_id, plate, timestamp, evidence_ref, previous_hash). Any alteration to electronic record changes hash and is detected. Hash chain links this evidence to previous records ensuring chronological integrity per BSA 2023.</p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-line bg-white p-3"><p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Certificate ID</p><p className="mt-1 font-mono text-xs font-bold">{c.certificate_id ?? '—'}</p><p className="mt-1 text-[10px] text-ink-faint">BSA 2023 Section 63</p></div>
          <div className="rounded-xl border border-line bg-white p-3"><p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Digital Signature</p><p className="mt-1 font-mono text-xs font-bold truncate">{c.certification?.digital_signature ?? '—'}</p><p className="mt-1 text-[10px] text-ink-faint">Signed by {c.certification?.certified_by ?? 'System'}</p></div>
          <div className="rounded-xl border border-line bg-white p-3"><p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Case Number</p><p className="mt-1 font-mono text-xs font-bold">{c.certification?.case_number ?? '—'}</p><p className="mt-1 text-[10px] text-ink-faint">Gujarat Police Jurisdiction</p></div>
          <div className={`rounded-xl border p-3 ${admissible ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
            <p className={`text-[10px] font-bold uppercase tracking-widest ${admissible ? 'text-emerald-700' : 'text-red-700'}`}>Court Admissible</p>
            <p className={`mt-1 flex items-center gap-1 font-mono text-xs font-bold ${admissible ? 'text-emerald-800' : 'text-red-800'}`}>
              <Lock size={12} /> {admissible ? 'YES • Sec 65B' : 'NO — INTEGRITY FAILED'}
            </p>
            <p className={`mt-1 text-[10px] ${admissible ? 'text-emerald-700' : 'text-red-700'}`}>
              {admissible
                ? `BSA 2023 • Hash chain ${v?.chain_integrity ?? 'verified'}`
                : (v?.findings?.join(', ') || 'Verification unavailable')}
            </p>
          </div>
        </div>

        {!intact && (v?.modified_fields?.length || v?.findings?.length) ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3.5">
            <p className="text-[11px] font-bold text-red-800">Integrity findings</p>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-red-700">
              {(v?.findings ?? []).map((f) => (
                <li key={f} className="font-mono">{f}</li>
              ))}
              {(v?.modified_fields ?? []).map((m) => (
                <li key={m.field} className="font-mono">
                  {m.field}: sealed {String(m.sealed ?? '—')} → now {String(m.current ?? '—')}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 to-indigo-50 p-4">
          <p className="flex items-center gap-1.5 text-[11px] font-bold text-blue-800"><FileCheck size={14} /> Legal Compliance — BSA 2023 Section 63 & Section 65B Indian Evidence Act</p>
          <div className="mt-3 grid gap-3 text-[11px] leading-relaxed text-blue-900 sm:grid-cols-3">
            <div><p className="font-bold">BSA 2023 Sec 63</p><p className="mt-1 text-blue-800">{(c.legal_statements?.bsa_2023_section_63 ?? '').slice(0, 220)}...</p></div>
            <div><p className="font-bold">Sec 65B Compliance</p><p className="mt-1 text-blue-800">{(c.legal_statements?.section_65b ?? '').slice(0, 220)}...</p></div>
            <div><p className="font-bold">Tamper-Proof Guarantee</p><p className="mt-1 text-blue-800">{(c.legal_statements?.tamper_proof ?? '').slice(0, 220)}...</p></div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button className="btn-primary gap-1.5 text-xs" onClick={() => window.print()}><Download size={14} /> Download Certificate (PDF Ready)</button>
          <button className="btn-ghost gap-1.5 text-xs" onClick={() => verify.refresh()}><Verified size={14} /> Verify Hash Chain</button>
          <span className="chip border-slate-200 bg-slate-50 text-ink-faint text-[10px] font-mono">Verification: /api/reports/evidence/{String(eventId)}/verify • QR: TRINETRA:{c.certificate_id}</span>
        </div>
      </div>
    </div>
  );
}
