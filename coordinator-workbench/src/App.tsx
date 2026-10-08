import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL ?? 'http://localhost:8000/api/v1';

type Patient = {
  id: string;
  external_id: string;
  given_name: string;
  family_name: string;
  email: string;
  study_id: string;
  site_id: string;
  is_active: boolean;
};

type ConversationMessage = {
  id: string;
  sender: 'patient' | 'coordinator';
  body: string;
  created_at: string;
};

type Appointment = {
  id: string;
  patient_id: string;
  title: string;
  location: string | null;
  starts_at: string;
  status: 'scheduled' | 'cancelled';
};

export default function App() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [readiness, setReadiness] = useState('Checking');
  const [database, setDatabase] = useState('Checking');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [inviteCode, setInviteCode] = useState('');
  const [invitePatient, setInvitePatient] = useState('');
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [replyDraft, setReplyDraft] = useState('');
  const [appointmentPatient, setAppointmentPatient] = useState<Patient | null>(null);
  const [appointmentTitle, setAppointmentTitle] = useState('Doctor appointment');
  const [appointmentLocation, setAppointmentLocation] = useState('');
  const [appointmentTime, setAppointmentTime] = useState('');
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const loadWorkbench = useCallback(async () => {
    setError('');
    try {
      const [readinessResponse, patientsResponse] = await Promise.all([
        fetch(`${CORE_API_URL}/readiness`),
        fetch(`${CORE_API_URL}/patients?limit=100`),
      ]);
      if (!readinessResponse.ok || !patientsResponse.ok) {
        throw new Error('The core service returned an error while loading the workbench.');
      }
      const readinessData = await readinessResponse.json();
      const patientData: Patient[] = await patientsResponse.json();
      setReadiness(readinessData.status ?? 'unknown');
      setDatabase(readinessData.database?.message ?? 'unknown');
      setPatients(patientData);
    } catch (loadError) {
      setReadiness('offline');
      setDatabase('offline');
      setError(loadError instanceof Error ? loadError.message : 'Could not load patients.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkbench();
  }, [loadWorkbench]);

  const visiblePatients = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return patients;
    return patients.filter((patient) =>
      [
        patient.external_id,
        patient.given_name,
        patient.family_name,
        patient.email,
        patient.study_id,
        patient.site_id,
      ].some((value) => value.toLowerCase().includes(term)),
    );
  }, [patients, search]);

  const togglePatient = async (patient: Patient) => {
    setUpdatingId(patient.id);
    setError('');
    try {
      const response = patient.is_active
        ? await fetch(`${CORE_API_URL}/patients/${patient.id}`, { method: 'DELETE' })
        : await fetch(`${CORE_API_URL}/patients/${patient.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: true }),
          });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? 'Could not update this patient.');
      }
      await loadWorkbench();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : 'Could not update this patient.');
    } finally {
      setUpdatingId(null);
    }
  };

  const createInvite = async (patient: Patient) => {
    setUpdatingId(patient.id);
    setError('');
    setInviteCode('');
    setInvitePatient('');
    try {
      const response = await fetch(`${CORE_API_URL}/auth/patients/${patient.id}/invite`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not create an activation code.');
      setInviteCode(data.invite_code);
      setInvitePatient(`${patient.given_name} ${patient.family_name}`);
    } catch (inviteError) {
      setError(inviteError instanceof Error ? inviteError.message : 'Could not create an activation code.');
    } finally {
      setUpdatingId(null);
    }
  };

  const openConversation = async (patient: Patient) => {
    setSelectedPatient(patient);
    setConversation([]);
    setError('');
    try {
      const response = await fetch(`${CORE_API_URL}/coordinator/patients/${patient.id}/messages`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not load the conversation.');
      setConversation(data);
    } catch (conversationError) {
      setError(conversationError instanceof Error ? conversationError.message : 'Could not load the conversation.');
    }
  };

  const sendCoordinatorReply = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedPatient) return;
    setUpdatingId(selectedPatient.id);
    setError('');
    try {
      const response = await fetch(`${CORE_API_URL}/coordinator/patients/${selectedPatient.id}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: replyDraft }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not send the reply.');
      setConversation((current) => [...current, data]);
      setReplyDraft('');
    } catch (replyError) {
      setError(replyError instanceof Error ? replyError.message : 'Could not send the reply.');
    } finally {
      setUpdatingId(null);
    }
  };

  const loadAppointments = async (patient: Patient) => {
    setAppointmentPatient(patient);
    setAppointments([]);
    setError('');
    try {
      const response = await fetch(`${CORE_API_URL}/coordinator/patients/${patient.id}/appointments`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not load appointments.');
      setAppointments(data);
    } catch (appointmentError) {
      setError(appointmentError instanceof Error ? appointmentError.message : 'Could not load appointments.');
    }
  };

  const scheduleAppointment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!appointmentPatient) return;
    setUpdatingId(appointmentPatient.id);
    setError('');
    try {
      const response = await fetch(
        `${CORE_API_URL}/coordinator/patients/${appointmentPatient.id}/appointments`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: appointmentTitle,
            location: appointmentLocation || null,
            starts_at: new Date(appointmentTime).toISOString(),
          }),
        },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not schedule the appointment.');
      setAppointments((current) => [...current, data].sort(
        (left, right) => Date.parse(left.starts_at) - Date.parse(right.starts_at),
      ));
      setAppointmentTime('');
      setAppointmentTitle('Doctor appointment');
      setAppointmentLocation('');
    } catch (scheduleError) {
      setError(scheduleError instanceof Error ? scheduleError.message : 'Could not schedule the appointment.');
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <main className="min-h-screen bg-slate-900 p-5 text-slate-50 sm:p-8">
      <div className="mx-auto max-w-6xl rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-xl sm:p-8">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Coordinator Workbench</p>
        <p className="mt-3 text-sm font-semibold text-slate-400">Clinical Connect AI</p>
        <h1 className="mt-3 text-3xl font-bold">Patient management</h1>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
            <p className="text-sm text-slate-400">Service readiness</p>
            <p className="mt-2 text-xl font-semibold capitalize">{readiness}</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
            <p className="text-sm text-slate-400">Database status</p>
            <p className="mt-2 text-xl font-semibold">{database}</p>
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <label className="block w-full sm:max-w-md">
            <span className="text-sm font-medium text-slate-300">Search patients</span>
            <input
              className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white outline-none focus:border-cyan-400"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name, email, study, site, or patient ID"
            />
          </label>
          <button
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold hover:bg-slate-700"
            onClick={() => void loadWorkbench()}
            type="button"
          >
            Refresh
          </button>
        </div>

        {error && <p role="alert" className="mt-4 rounded-lg bg-red-950 p-3 text-red-200">{error}</p>}
        {inviteCode && (
          <section className="mt-4 rounded-xl border border-amber-700 bg-amber-950 p-4" aria-label="Patient activation code">
            <h2 className="font-semibold">One-time code for {invitePatient}</h2>
            <p className="mt-2 break-all font-mono text-lg text-amber-200">{inviteCode}</p>
            <p className="mt-2 text-sm text-amber-100">Share this code securely with the patient. It expires in 72 hours and is shown only once.</p>
          </section>
        )}
        <div className="mt-5 overflow-x-auto rounded-xl border border-slate-700">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-slate-900 text-slate-300">
              <tr>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Study / site</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {loading ? (
                <tr><td className="px-4 py-5 text-slate-400" colSpan={4}>Loading patients...</td></tr>
              ) : visiblePatients.length === 0 ? (
                <tr><td className="px-4 py-5 text-slate-400" colSpan={4}>No patients found.</td></tr>
              ) : visiblePatients.map((patient) => (
                <tr key={patient.id} className="bg-slate-800">
                  <td className="px-4 py-3">
                    <p className="font-medium">{patient.given_name} {patient.family_name}</p>
                    <p className="mt-1 text-slate-400">{patient.external_id} · {patient.email}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{patient.study_id} / {patient.site_id}</td>
                  <td className="px-4 py-3">
                    <span className={patient.is_active ? 'text-green-300' : 'text-slate-400'}>
                      {patient.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="flex gap-2 px-4 py-3">
                    <button
                      className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold hover:bg-slate-700"
                      onClick={() => void openConversation(patient)}
                      type="button"
                    >
                      Messages
                    </button>
                    <button
                      className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold hover:bg-slate-700"
                      onClick={() => void loadAppointments(patient)}
                      type="button"
                    >
                      Appointments
                    </button>
                    <button
                      className="rounded-md border border-cyan-700 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-slate-700 disabled:opacity-50"
                      disabled={updatingId === patient.id || !patient.is_active}
                      onClick={() => void createInvite(patient)}
                      type="button"
                    >
                      Create sign-up code
                    </button>
                    <button
                      className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold hover:bg-slate-700 disabled:opacity-50"
                      disabled={updatingId === patient.id}
                      onClick={() => void togglePatient(patient)}
                      type="button"
                    >
                      {updatingId === patient.id ? 'Saving...' : patient.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selectedPatient && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
            <section
              className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl"
              aria-label={`Conversation with ${selectedPatient.given_name} ${selectedPatient.family_name}`}
              aria-modal="true"
              role="dialog"
            >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Conversation with {selectedPatient.given_name} {selectedPatient.family_name}</h2>
                <p className="mt-1 text-sm text-slate-400">{selectedPatient.external_id} · {selectedPatient.email}</p>
              </div>
              <button className="rounded border border-slate-600 px-3 py-1 text-sm hover:bg-slate-800" onClick={() => setSelectedPatient(null)} type="button">
                Close
              </button>
            </div>
            <div className="mt-4 max-h-72 space-y-3 overflow-y-auto rounded-lg bg-slate-800 p-3" aria-live="polite">
              {conversation.length === 0 ? (
                <p className="text-sm text-slate-400">No messages yet.</p>
              ) : conversation.map((message) => (
                <article className={`max-w-[90%] rounded-lg p-3 ${message.sender === 'coordinator' ? 'ml-auto bg-cyan-950' : 'bg-slate-700'}`} key={message.id}>
                  <p className="mb-1 text-xs font-semibold text-slate-300">{message.sender === 'coordinator' ? 'Coordinator' : 'Patient'}</p>
                  <p className="whitespace-pre-wrap break-words text-sm">{message.body}</p>
                  <time className="mt-2 block text-right text-[11px] text-slate-400" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
                </article>
              ))}
            </div>
            <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={sendCoordinatorReply}>
              <label className="flex-1">
                <span className="sr-only">Reply to patient</span>
                <textarea className="min-h-16 w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white" maxLength={4000} onChange={(event) => setReplyDraft(event.target.value)} required value={replyDraft} />
              </label>
              <button className="self-end rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={updatingId === selectedPatient.id} type="submit">
                {updatingId === selectedPatient.id ? 'Sending...' : 'Send reply'}
              </button>
            </form>
            </section>
          </div>
        )}
        {appointmentPatient && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
            <section
              className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl"
              aria-label={`Appointments for ${appointmentPatient.given_name} ${appointmentPatient.family_name}`}
              aria-modal="true"
              role="dialog"
            >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">Appointments for {appointmentPatient.given_name} {appointmentPatient.family_name}</h2>
                <p className="mt-1 text-sm text-slate-400">Times are entered in your browser’s local timezone. Two in-portal reminders are created 48 and 24 hours before the appointment.</p>
              </div>
              <button className="rounded border border-slate-600 px-3 py-1 text-sm hover:bg-slate-800" onClick={() => setAppointmentPatient(null)} type="button">
                Close
              </button>
            </div>
            <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={scheduleAppointment}>
              <label className="grid gap-1 text-sm font-medium text-slate-300">
                Appointment title
                <input className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" maxLength={160} onChange={(event) => setAppointmentTitle(event.target.value)} required value={appointmentTitle} />
              </label>
              <label className="grid gap-1 text-sm font-medium text-slate-300">
                Date and time
                <input className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" onChange={(event) => setAppointmentTime(event.target.value)} required type="datetime-local" value={appointmentTime} />
              </label>
              <label className="grid gap-1 text-sm font-medium text-slate-300 sm:col-span-2">
                Location (optional)
                <input className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" maxLength={255} onChange={(event) => setAppointmentLocation(event.target.value)} value={appointmentLocation} />
              </label>
              <button className="justify-self-start rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={updatingId === appointmentPatient.id} type="submit">
                {updatingId === appointmentPatient.id ? 'Scheduling...' : 'Schedule appointment'}
              </button>
            </form>
            <ul className="mt-4 divide-y divide-slate-700">
              {appointments.map((appointment) => (
                <li className="py-3" key={appointment.id}>
                  <p className="font-medium">{appointment.title}</p>
                  <p className="mt-1 text-sm text-slate-400">{new Date(appointment.starts_at).toLocaleString()}{appointment.location ? ` · ${appointment.location}` : ''}</p>
                </li>
              ))}
              {appointments.length === 0 && <li className="py-3 text-sm text-slate-400">No upcoming appointments.</li>}
            </ul>
            </section>
          </div>
        )}
        <p className="mt-5 text-xs text-slate-400">Synthetic demonstration records only. Do not use real patient data.</p>
      </div>
    </main>
  );
}
