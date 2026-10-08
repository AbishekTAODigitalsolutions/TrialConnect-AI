import { FormEvent, useCallback, useEffect, useState } from 'react';

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL ?? 'http://localhost:8000/api/v1';
const SESSION_KEY = 'clinical-connect-patient-session';

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

type AuthMode = 'login' | 'signup' | 'activate';
type PatientMessage = {
  id: string;
  sender: 'patient' | 'coordinator';
  body: string;
  created_at: string;
};

type PatientAppointment = {
  id: string;
  title: string;
  location: string | null;
  starts_at: string;
};

type AssistantSource = {
  title: string;
  url: string;
};

type AssistantAnswer = {
  answer: string;
  sources: AssistantSource[];
};

type PortalSection = 'messages' | 'faq';

function responseMessage(data: { detail?: string | Array<{ msg?: string }> }, fallback: string): string {
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg ?? 'Invalid input').join(', ');
  return fallback;
}

export default function App() {
  const [mode, setMode] = useState<AuthMode>('login');
  const [patient, setPatient] = useState<Patient | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [givenName, setGivenName] = useState('');
  const [familyName, setFamilyName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [section, setSection] = useState<PortalSection>('messages');
  const [messages, setMessages] = useState<PatientMessage[]>([]);
  const [messageDraft, setMessageDraft] = useState('');
  const [faqQuestion, setFaqQuestion] = useState('');
  const [faqAnswer, setFaqAnswer] = useState<AssistantAnswer | null>(null);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [appointments, setAppointments] = useState<PatientAppointment[]>([]);
  const [loadingAppointments, setLoadingAppointments] = useState(false);

  const loadAppointments = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoadingAppointments(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const appointmentsResponse = await fetch(`${CORE_API_URL}/appointments`, { headers });
      const appointmentData = await appointmentsResponse.json();
      if (!appointmentsResponse.ok) throw new Error(responseMessage(appointmentData, 'Could not load appointments.'));
      setAppointments(appointmentData);
    } catch (appointmentError) {
      setError(appointmentError instanceof Error ? appointmentError.message : 'Could not load appointments.');
    } finally {
      setLoadingAppointments(false);
    }
  }, []);

  const loadMessages = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoadingMessages(true);
    try {
      const response = await fetch(`${CORE_API_URL}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not load messages.'));
      setMessages(data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load messages.');
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (patient) void loadMessages();
  }, [patient, loadMessages]);

  useEffect(() => {
    if (!patient) return;
    void loadAppointments();
    const intervalId = window.setInterval(() => void loadAppointments(), 60_000);
    return () => window.clearInterval(intervalId);
  }, [patient, loadAppointments]);

  useEffect(() => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) {
      setCheckingSession(false);
      return;
    }
    void fetch(`${CORE_API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('Session expired');
        setPatient(await response.json());
      })
      .catch(() => sessionStorage.removeItem(SESSION_KEY))
      .finally(() => setCheckingSession(false));
  }, []);

  const submitAuth = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    const endpoint = mode === 'login' ? '/auth/login' : mode === 'signup' ? '/auth/signup' : '/auth/activate';
    const body = mode === 'login'
      ? { email, password }
      : mode === 'signup'
        ? { given_name: givenName, family_name: familyName, email, password }
        : { email, invite_code: inviteCode, password };

    try {
      const response = await fetch(`${CORE_API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not authenticate.'));
      sessionStorage.setItem(SESSION_KEY, data.access_token);
      setPatient(data.patient);
      setSection('messages');
      setPassword('');
      setInviteCode('');
    } catch (authError) {
      setError(authError instanceof Error ? authError.message : 'Could not authenticate.');
    } finally {
      setLoading(false);
    }
  };

  const logOut = () => {
    sessionStorage.removeItem(SESSION_KEY);
    setPatient(null);
    setPassword('');
    setMode('login');
  };

  const sendMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${CORE_API_URL}/messages`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: messageDraft }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not send your message.'));
      setMessages((current) => [...current, data]);
      setMessageDraft('');
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Could not send your message.');
    } finally {
      setLoading(false);
    }
  };

  const askFaq = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoading(true);
    setError('');
    setFaqAnswer(null);
    try {
      const response = await fetch(`${CORE_API_URL}/assistant/faq`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: faqQuestion }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not get an answer.'));
      setFaqAnswer(data as AssistantAnswer);
    } catch (faqError) {
      setError(faqError instanceof Error ? faqError.message : 'Could not get an answer.');
    } finally {
      setLoading(false);
    }
  };

  if (checkingSession) {
    return <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-600">Checking your session...</main>;
  }

  return (
    <main className="min-h-screen bg-slate-50 p-6 text-slate-900 sm:p-10">
      <div className="mx-auto max-w-2xl rounded-2xl bg-white p-6 shadow-lg sm:p-9">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-700">Patient Portal</p>
        <p className="mt-3 text-sm font-semibold text-slate-500">Clinical Connect AI</p>

        {patient ? (
          <section className="mt-5">
            <h1 className="text-3xl font-bold">Welcome, {patient.given_name}</h1>
            <p className="mt-2 text-slate-600">You are signed in to your patient account.</p>
            <dl className="mt-7 grid gap-4 rounded-xl bg-slate-50 p-5 sm:grid-cols-2">
              <div><dt className="text-sm text-slate-500">Patient ID</dt><dd className="mt-1 font-medium">{patient.external_id}</dd></div>
              <div><dt className="text-sm text-slate-500">Email</dt><dd className="mt-1 font-medium">{patient.email}</dd></div>
              <div><dt className="text-sm text-slate-500">Study</dt><dd className="mt-1 font-medium">{patient.study_id}</dd></div>
              <div><dt className="text-sm text-slate-500">Site</dt><dd className="mt-1 font-medium">{patient.site_id}</dd></div>
            </dl>
            {appointments.length > 0 && (
              <section className="mt-7 rounded-xl border border-blue-100 bg-blue-50 p-4" aria-label="Upcoming scheduled appointments">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-blue-950">Upcoming scheduled appointments</h2>
                  <button className="rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm font-semibold text-blue-900 disabled:opacity-60" disabled={loadingAppointments} onClick={() => void loadAppointments()} type="button">
                    {loadingAppointments ? 'Refreshing...' : 'Refresh appointments'}
                  </button>
                </div>
                <ul className="mt-2 divide-y divide-blue-100">
                  {appointments.map((appointment) => (
                    <li className="py-2" key={appointment.id}>
                      <p className="font-medium text-slate-900">{appointment.title}</p>
                      <p className="mt-1 text-sm text-slate-700">
                        {new Date(appointment.starts_at).toLocaleString()}
                        {appointment.location ? ` · ${appointment.location}` : ''}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <div className="mt-7 flex gap-2 border-b border-slate-200 pb-3">
              {([
                ['messages', 'Message coordinator'],
                ['faq', 'Study FAQ helper'],
              ] as const).map(([value, label]) => (
                <button
                  aria-pressed={section === value}
                  className={`rounded-lg px-3 py-2 text-sm font-semibold ${section === value ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                  key={value}
                  onClick={() => { setSection(value); setError(''); }}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
            {section === 'messages' ? (
              <section className="mt-5" aria-label="Conversation with coordinator">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold">Conversation with your study coordinator</h2>
                    <p className="mt-1 text-sm text-slate-600">Send non-urgent study questions. This is not for medical emergencies.</p>
                  </div>
                  <button className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-60" disabled={loadingMessages} onClick={() => void loadMessages()} type="button">
                    {loadingMessages ? 'Refreshing...' : 'Refresh conversation'}
                  </button>
                </div>
                <div className="mt-4 max-h-80 space-y-3 overflow-y-auto rounded-xl bg-slate-50 p-4" aria-live="polite">
                  {loadingMessages && messages.length === 0 ? (
                    <p className="text-sm text-slate-500">Loading conversation...</p>
                  ) : messages.length === 0 ? (
                    <p className="text-sm text-slate-500">No messages yet. Send a message to start your conversation.</p>
                  ) : messages.map((message) => (
                    <article className={`max-w-[90%] rounded-xl p-3 ${message.sender === 'patient' ? 'ml-auto bg-blue-100' : 'bg-white shadow-sm'}`} key={message.id}>
                      <p className="mb-1 text-xs font-semibold text-slate-500">{message.sender === 'patient' ? 'You' : 'Study coordinator'}</p>
                      <p className="whitespace-pre-wrap break-words text-sm">{message.body}</p>
                      <time className="mt-2 block text-right text-[11px] text-slate-500" dateTime={message.created_at}>
                        {new Date(message.created_at).toLocaleString()}
                      </time>
                    </article>
                  ))}
                </div>
                <form className="mt-3 grid gap-2" onSubmit={sendMessage}>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Your message
                    <textarea className="min-h-24 rounded-lg border border-slate-300 px-3 py-2" maxLength={4000} onChange={(event) => setMessageDraft(event.target.value)} required value={messageDraft} />
                  </label>
                  {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
                  <button className="justify-self-start rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={loading} type="submit">
                    {loading ? 'Sending...' : 'Send message'}
                  </button>
                </form>
              </section>
            ) : (
              <section className="mt-5" aria-label="Study FAQ helper">
                <h2 className="text-xl font-semibold">AI web search helper</h2>
                <p className="mt-1 text-sm text-slate-600">When configured, this helper searches the public web for non-medical questions and cites sources. Questions are sent to OpenAI. Do not include identifying or health information. It can’t answer medical questions or give health advice.</p>
                <form className="mt-4 grid gap-3" onSubmit={askFaq}>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Ask about study participation, appointments, account access, or privacy
                    <textarea className="min-h-20 rounded-lg border border-slate-300 px-3 py-2" maxLength={1000} onChange={(event) => setFaqQuestion(event.target.value)} required value={faqQuestion} />
                  </label>
                  {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
                  <button className="justify-self-start rounded-lg bg-blue-700 px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={loading} type="submit">
                    {loading ? 'Checking...' : 'Ask FAQ helper'}
                  </button>
                </form>
                {faqAnswer && (
                  <div aria-live="polite" className="mt-4 rounded-xl bg-blue-50 p-4 text-sm leading-relaxed text-blue-950">
                    <p className="whitespace-pre-wrap">{faqAnswer.answer}</p>
                    {faqAnswer.sources.length > 0 && (
                      <div className="mt-3 border-t border-blue-200 pt-3">
                        <h3 className="font-semibold">Sources</h3>
                        <ul className="mt-1 list-inside list-disc">
                          {faqAnswer.sources.map((source) => (
                            <li key={source.url}>
                              <a className="text-blue-800 underline" href={source.url} rel="noopener noreferrer" target="_blank">
                                {source.title}
                              </a>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}
            <button className="mt-6 rounded-lg border border-slate-300 px-4 py-2 font-semibold hover:bg-slate-50" onClick={logOut} type="button">
              Log out
            </button>
          </section>
        ) : (
          <>
            <h1 className="mt-1 text-3xl font-bold">
              {mode === 'login' ? 'Log in' : mode === 'signup' ? 'Create your patient account' : 'Activate your patient account'}
            </h1>
            <p className="mt-2 text-slate-600">
              {mode === 'login'
                ? 'Already have an account? Log in with your email and password.'
                : mode === 'signup'
                  ? 'New to Clinical Connect AI? Create a patient account.'
                  : 'Have an existing patient record? Use the one-time code from your coordinator.'}
            </p>

            <div className="mt-6 flex flex-wrap gap-2 border-b border-slate-200 pb-4">
              {([
                ['login', 'Log in'],
                ['signup', 'Sign up'],
                ['activate', 'Existing patient'],
              ] as const).map(([value, label]) => (
                <button
                  aria-pressed={mode === value}
                  className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === value ? 'bg-blue-700 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                  key={value}
                  onClick={() => { setMode(value); setError(''); }}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>

            <form className="mt-6 grid gap-4" onSubmit={submitAuth}>
              {mode === 'signup' && (
                <>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Given name
                    <input autoComplete="given-name" className="rounded-lg border border-slate-300 px-3 py-2" maxLength={128} onChange={(event) => setGivenName(event.target.value)} required value={givenName} />
                  </label>
                  <label className="grid gap-1 text-sm font-medium text-slate-700">
                    Family name
                    <input autoComplete="family-name" className="rounded-lg border border-slate-300 px-3 py-2" maxLength={128} onChange={(event) => setFamilyName(event.target.value)} required value={familyName} />
                  </label>
                </>
              )}
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                Email address
                <input autoComplete="email" className="rounded-lg border border-slate-300 px-3 py-2" maxLength={255} onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
              </label>
              {mode === 'activate' && (
                <label className="grid gap-1 text-sm font-medium text-slate-700">
                  One-time activation code
                  <input autoComplete="one-time-code" className="rounded-lg border border-slate-300 px-3 py-2" onChange={(event) => setInviteCode(event.target.value)} required value={inviteCode} />
                </label>
              )}
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                Password
                <input
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  className="rounded-lg border border-slate-300 px-3 py-2"
                  minLength={mode === 'login' ? 1 : 12}
                  maxLength={128}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
                {mode !== 'login' && <span className="text-xs font-normal text-slate-500">Use at least 12 characters.</span>}
              </label>
              {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
              <button className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white hover:bg-blue-800 disabled:opacity-60" disabled={loading} type="submit">
                {loading ? 'Please wait...' : mode === 'login' ? 'Log in' : mode === 'signup' ? 'Sign up' : 'Activate account'}
              </button>
            </form>
          </>
        )}

        <p className="mt-8 border-t border-slate-200 pt-4 text-xs text-slate-500">
          Synthetic demonstration only. Do not enter real patient information.
        </p>
      </div>
    </main>
  );
}
