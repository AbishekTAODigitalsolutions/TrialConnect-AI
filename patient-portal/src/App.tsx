import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL ?? 'http://localhost:8000/api/v1';
const SESSION_KEY = 'clinical-connect-patient-session';

type Patient = {
  given_name: string;
};

type AuthMode = 'login' | 'signup';
type PatientMessage = {
  id: string;
  sender: 'patient' | 'coordinator';
  body: string;
  created_at: string;
  read_at: string | null;
};

type PatientAppointment = {
  id: string;
  title: string;
  location: string | null;
  starts_at: string;
};

type PatientNotification = {
  id: string;
  appointment_id: string;
  reminder_type: 'scheduled' | '48_hours' | '24_hours';
  title: string;
  body: string;
  scheduled_for: string;
  created_at: string;
  read_at: string | null;
};

type AssistantSource = {
  title: string;
  url: string;
};

type AssistantAnswer = {
  answer: string;
  sources: AssistantSource[];
  category: string;
};

type FAQChatTurn = {
  id: string;
  question: string;
  created_at: string;
  answer: AssistantAnswer;
  error?: string;
};

type PortalSection = 'messages' | 'faq' | 'notifications' | 'settings' | 'about';
const TOAST_PREFERENCE_KEY = 'clinical-connect-patient-toast-enabled';
const FAQ_STARTER_QUESTIONS = [
  'What is a clinical study?',
  'How can I contact my study coordinator?',
  'What is a migraine?',
];
const COORDINATOR_HANDOFF_CATEGORIES = ['appointments', 'coordinator_redirect', 'medical_redirect'];

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
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [section, setSection] = useState<PortalSection>('messages');
  const [toastEnabled, setToastEnabled] = useState(
    () => localStorage.getItem(TOAST_PREFERENCE_KEY) !== 'false',
  );
  const [messages, setMessages] = useState<PatientMessage[]>([]);
  const [unreadMessages, setUnreadMessages] = useState<PatientMessage[]>([]);
  const [messageToast, setMessageToast] = useState('');
  const seenUnreadMessageIds = useRef(new Set<string>());
  const locallyReadMessageIds = useRef(new Set<string>());
  const unreadRequestId = useRef(0);
  const initializedUnreadMessages = useRef(false);
  const [messageDraft, setMessageDraft] = useState('');
  const [faqConversation, setFaqConversation] = useState<FAQChatTurn[]>([]);
  const [faqLoading, setFaqLoading] = useState(false);
  const [chatNotice, setChatNotice] = useState('');
  const faqConversationEndRef = useRef<HTMLDivElement | null>(null);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [appointments, setAppointments] = useState<PatientAppointment[]>([]);
  const [loadingAppointments, setLoadingAppointments] = useState(false);
  const [appointmentNotifications, setAppointmentNotifications] = useState<PatientNotification[]>([]);
  const [loadingNotifications, setLoadingNotifications] = useState(false);

  const handleUnauthorized = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setPatient(null);
    setMode('login');
    setSection('messages');
    setFaqConversation([]);
    setChatNotice('');
    setError('Your login session has expired. Please log in again to continue.');
  }, []);

  const loadAppointments = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoadingAppointments(true);
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const appointmentsResponse = await fetch(`${CORE_API_URL}/appointments`, { headers });
      if (appointmentsResponse.status === 401) {
        handleUnauthorized();
        return;
      }
      const appointmentData = await appointmentsResponse.json();
      if (!appointmentsResponse.ok) throw new Error(responseMessage(appointmentData, 'Could not load appointments.'));
      setAppointments(appointmentData);
    } catch (appointmentError) {
      setError(appointmentError instanceof Error ? appointmentError.message : 'Could not load appointments.');
    } finally {
      setLoadingAppointments(false);
    }
  }, [handleUnauthorized]);

  const loadAppointmentNotifications = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoadingNotifications(true);
    try {
      const response = await fetch(`${CORE_API_URL}/notifications?unread_only=true`, {
        headers: { Authorization: 'Bearer ' + token },
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not load appointment notifications.'));
      setAppointmentNotifications(data);
    } catch (notificationError) {
      setError(notificationError instanceof Error ? notificationError.message : 'Could not load appointment notifications.');
    } finally {
      setLoadingNotifications(false);
    }
  }, [handleUnauthorized]);

  const markAppointmentNotificationRead = async (notificationId: string) => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    try {
      const response = await fetch(`${CORE_API_URL}/notifications/${notificationId}/read`, {
        method: 'PATCH',
        headers: { Authorization: 'Bearer ' + token },
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      if (!response.ok) {
        const data = await response.json();
        throw new Error(responseMessage(data, 'Could not mark the appointment notification as read.'));
      }
      setAppointmentNotifications((current) => current.filter((notification) => notification.id !== notificationId));
    } catch (notificationError) {
      setError(notificationError instanceof Error ? notificationError.message : 'Could not mark the appointment notification as read.');
    }
  };

  const loadMessages = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    setLoadingMessages(true);
    try {
      const response = await fetch(`${CORE_API_URL}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not load messages.'));
      setMessages(data);
      const incomingIds = (data as PatientMessage[])
        .filter((message) => message.sender === 'coordinator' && message.read_at === null)
        .map((message) => message.id);
      if (incomingIds.length > 0) {
        const readResponse = await fetch(`${CORE_API_URL}/messages/read`, {
          method: 'PATCH',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message_ids: incomingIds }),
        });
        if (readResponse.status === 401) {
          handleUnauthorized();
          return;
        }
        if (!readResponse.ok) {
          const readData = await readResponse.json();
          throw new Error(responseMessage(readData, 'Could not mark messages as read.'));
        }
        incomingIds.forEach((messageId) => locallyReadMessageIds.current.add(messageId));
        unreadRequestId.current += 1;
        setUnreadMessages((current) => current.filter((message) => !incomingIds.includes(message.id)));
        setMessageToast('');
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load messages.');
    } finally {
      setLoadingMessages(false);
    }
  }, [handleUnauthorized]);

  const loadUnreadMessages = useCallback(async () => {
    const token = sessionStorage.getItem(SESSION_KEY);
    if (!token) return;
    const requestId = ++unreadRequestId.current;
    try {
      const response = await fetch(`${CORE_API_URL}/messages/unread`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not check for new messages.'));
      if (requestId !== unreadRequestId.current) return;
      const unread: PatientMessage[] = data.filter(
        (message: PatientMessage) => !locallyReadMessageIds.current.has(message.id),
      );
      if (initializedUnreadMessages.current) {
        const newMessage = unread.find((message) => !seenUnreadMessageIds.current.has(message.id));
        if (newMessage && toastEnabled) {
          setMessageToast('You received a new message from your study coordinator.');
        }
      }
      unread.forEach((message) => seenUnreadMessageIds.current.add(message.id));
      initializedUnreadMessages.current = true;
      setUnreadMessages(unread);
    } catch (notificationError) {
      setError(notificationError instanceof Error ? notificationError.message : 'Could not check for new messages.');
    }
  }, [handleUnauthorized, toastEnabled]);

  useEffect(() => {
    if (patient) void loadMessages();
  }, [patient, loadMessages]);

  useEffect(() => {
    if (!patient || section !== 'messages') return;
    const intervalId = window.setInterval(() => void loadMessages(), 15_000);
    return () => window.clearInterval(intervalId);
  }, [patient, section, loadMessages]);

  useEffect(() => {
    if (!patient) {
      setUnreadMessages([]);
      setMessageToast('');
      seenUnreadMessageIds.current.clear();
      locallyReadMessageIds.current.clear();
      unreadRequestId.current += 1;
      initializedUnreadMessages.current = false;
      return;
    }
    void loadUnreadMessages();
    const intervalId = window.setInterval(() => void loadUnreadMessages(), 15_000);
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void loadUnreadMessages();
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [patient, loadUnreadMessages]);

  useEffect(() => {
    if (!patient) return;
    void loadAppointments();
    const intervalId = window.setInterval(() => void loadAppointments(), 60_000);
    return () => window.clearInterval(intervalId);
  }, [patient, loadAppointments]);

  useEffect(() => {
    if (!patient) {
      setAppointmentNotifications([]);
      return;
    }
    void loadAppointmentNotifications();
    const intervalId = window.setInterval(() => void loadAppointmentNotifications(), 60_000);
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void loadAppointments();
        void loadAppointmentNotifications();
      }
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [patient, loadAppointments, loadAppointmentNotifications]);

  useEffect(() => {
    faqConversationEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [faqConversation, faqLoading, messages]);

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
        if (response.status === 401) {
          handleUnauthorized();
          return;
        }
        if (!response.ok) throw new Error('Could not verify your login session.');
        setPatient(await response.json());
      })
      .catch((sessionError) => {
        setError(sessionError instanceof Error ? sessionError.message : 'Could not verify your login session.');
      })
      .finally(() => setCheckingSession(false));
  }, [handleUnauthorized]);

  const submitAuth = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    const endpoint = mode === 'login' ? '/auth/login' : '/auth/signup';
    const body = mode === 'login'
      ? { email, password }
      : { given_name: givenName, family_name: familyName, email, password };

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
      setFaqConversation([]);
      setChatNotice('');
      setPassword('');
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
    setSection('messages');
    setFaqConversation([]);
    setChatNotice('');
  };

  const sendChatQuestion = async (rawQuestion: string) => {
    const token = sessionStorage.getItem(SESSION_KEY);
    const question = rawQuestion.trim();
    if (!token || !question || faqLoading) return;
    setFaqLoading(true);
    setMessageDraft('');
    setChatNotice('');
    setError('');

    const forwardToCoordinator = async (reason?: string): Promise<void> => {
      const response = await fetch(`${CORE_API_URL}/messages`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ body: question }),
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      const data = await response.json();
      if (!response.ok) throw new Error(responseMessage(data, 'Could not forward your question to the coordinator.'));
      setMessages((current) => [...current, data as PatientMessage]);
      setChatNotice(
        reason
          ? `The assistant is unavailable, so your question was sent to your study coordinator.`
          : `The assistant could not answer that. Your question was sent to your study coordinator.`,
      );
    };

    try {
      let answer: AssistantAnswer | null = null;
      let assistantUnavailable = false;
      try {
        const assistantResponse = await fetch(`${CORE_API_URL}/assistant/faq`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
        });
        if (assistantResponse.status === 401) {
          handleUnauthorized();
          return;
        }
        const assistantData = await assistantResponse.json();
        if (assistantResponse.ok) {
          answer = assistantData as AssistantAnswer;
        } else {
          assistantUnavailable = true;
        }
      } catch {
        assistantUnavailable = true;
      }

      if (!answer || COORDINATOR_HANDOFF_CATEGORIES.includes(answer.category)) {
        await forwardToCoordinator(assistantUnavailable ? 'assistant_unavailable' : undefined);
        return;
      }

      setFaqConversation((current) => [
        ...current,
        { id: crypto.randomUUID(), question, created_at: new Date().toISOString(), answer },
      ]);
    } catch (sendError) {
      setMessageDraft(question);
      setError(sendError instanceof Error ? sendError.message : 'Could not send your question.');
    } finally {
      setFaqLoading(false);
    }
  };

  const sendMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void sendChatQuestion(messageDraft);
  };

  const chatItems = [
    ...messages.map((message) => ({
      kind: 'message' as const,
      created_at: message.created_at,
      message,
    })),
    ...faqConversation.map((turn) => ({
      kind: 'assistant' as const,
      created_at: turn.created_at,
      turn,
    })),
  ].sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at));

  if (checkingSession) {
    return <main className="grid min-h-screen place-items-center bg-slate-50 text-slate-600">Checking your session...</main>;
  }

  return (
    <main className="min-h-screen bg-[#f3f6fa] px-4 py-5 text-slate-900 sm:px-8 sm:py-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-7 flex items-center justify-between rounded-2xl border border-slate-200/80 bg-white px-5 py-4 shadow-sm sm:px-7">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-teal-600 to-cyan-700 text-white shadow-md shadow-teal-900/15" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
                <path d="M12 3.5v17M3.5 12h17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" opacity=".75" />
              </svg>
            </div>
            <div>
              <p className="text-base font-bold tracking-tight text-slate-900">Clinical Connect AI</p>
              <p className="text-xs font-medium tracking-wide text-slate-500">PATIENT PORTAL</p>
            </div>
          </div>
          {patient && (
            <div className="hidden items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 sm:flex">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Secure session
            </div>
          )}
        </header>

        {patient ? (
          <section className="grid gap-6 lg:grid-cols-[250px_minmax(0,1fr)]">
            <aside className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:sticky lg:top-6 lg:self-start">
              <p className="mb-3 px-3 text-xs font-bold uppercase tracking-[0.14em] text-slate-400">Your workspace</p>
              <nav aria-label="Patient portal navigation" className="grid gap-1">
                {([
                  ['messages', 'Messages & AI'],
                  ['notifications', 'Notifications'],
                  ['settings', 'Settings'],
                  ['about', 'About'],
                ] as const).map(([value, label]) => (
                  <button
                    aria-current={section === value ? 'page' : undefined}
                    className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition-colors ${
                      section === value ? 'bg-teal-700 text-white shadow-sm shadow-teal-900/15' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                    key={value}
                    onClick={() => {
                      setSection(value);
                      setError('');
                      if (value === 'messages') void loadMessages();
                    }}
                    type="button"
                  >
                    <span>{label}</span>
                    {value === 'notifications' && unreadMessages.length + appointmentNotifications.length > 0 && (
                      <span className={`rounded-full px-2 py-0.5 text-xs ${
                        section === value ? 'bg-white text-teal-800' : 'bg-teal-50 text-teal-800'
                      }`}>{unreadMessages.length + appointmentNotifications.length}</span>
                    )}
                  </button>
                ))}
              </nav>
              <button className="mt-5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50" onClick={logOut} type="button">
                Log out
              </button>
            </aside>
            <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8">
            <div className="mb-7 flex flex-wrap items-end justify-between gap-4 border-b border-slate-100 pb-6">
              <div>
                <p className="text-sm font-semibold text-teal-700">Patient dashboard</p>
                <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950">Welcome, {patient.given_name}</h1>
                <p className="mt-2 text-sm text-slate-500">Your study updates and support, all in one place.</p>
              </div>
              <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                <span className="font-semibold text-slate-800">Need help?</span> Message your coordinator
              </div>
            </div>
            {messageToast && (
              <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-teal-200 bg-teal-50 p-4 text-sm text-teal-950" role="status">
                <span>{messageToast}</span>
                <button
                  className="font-semibold underline"
                  onClick={() => { setMessageToast(''); setSection('messages'); void loadMessages(); }}
                  type="button"
                >
                  View messages
                </button>
              </div>
            )}
            {section === 'messages' && appointments.length > 0 && (
              <section className="mt-7 rounded-2xl border border-teal-100 bg-gradient-to-br from-teal-50 to-cyan-50 p-5" aria-label="Upcoming scheduled appointments">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-slate-900">Upcoming appointments & reminders</h2>
                  <button className="rounded-xl border border-teal-200 bg-white px-3 py-2 text-sm font-semibold text-teal-800 transition-colors hover:bg-teal-50 disabled:opacity-60" disabled={loadingAppointments} onClick={() => void loadAppointments()} type="button">
                    {loadingAppointments ? 'Refreshing...' : 'Refresh appointments'}
                  </button>
                </div>
                <ul className="mt-3 divide-y divide-teal-100">
                  {appointments.map((appointment) => (
                    <li className="py-2" key={appointment.id}>
                      <p className="font-medium text-slate-900">{appointment.title}</p>
                      <p className="mt-1 text-sm text-slate-600">
                        {new Date(appointment.starts_at).toLocaleString()}
                        {appointment.location ? ` · ${appointment.location}` : ''}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2" aria-label="Appointment reminder schedule">
                        <span className="rounded-full border border-teal-200 bg-white/80 px-3 py-1 text-xs font-semibold text-teal-800">48-hour reminder</span>
                        <span className="rounded-full border border-teal-200 bg-white/80 px-3 py-1 text-xs font-semibold text-teal-800">24-hour reminder</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {section === 'messages' ? (
              <section className="mt-5 flex h-[min(76vh,820px)] min-h-[560px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white" aria-label="Messages and study assistant">
                <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-6">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-teal-600 to-cyan-700 text-white shadow-sm" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
                        <path d="M12 3.5v17M3.5 12h17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                        <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <h2 className="truncate text-base font-bold text-slate-900 sm:text-lg">Messages & study assistant</h2>
                      <p className="mt-0.5 text-xs text-slate-500">AI answers common questions; other questions go to your coordinator.</p>
                    </div>
                  </div>
                  <button className="shrink-0 rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 disabled:opacity-40 sm:text-sm" disabled={loadingMessages || faqLoading} onClick={() => void loadMessages()} type="button">
                    {loadingMessages ? 'Refreshing...' : 'Refresh'}
                  </button>
                </header>

                <div className="flex-1 overflow-y-auto bg-[#fbfcfd] px-4 py-5 sm:px-8 sm:py-7" role="log" aria-label="Conversation" aria-live="polite">
                  {loadingMessages && chatItems.length === 0 ? (
                    <p className="text-sm text-slate-500">Loading conversation...</p>
                  ) : chatItems.length === 0 ? (
                    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center">
                      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-teal-50 text-teal-700" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7">
                          <path d="M7.5 9h9m-9 4h5m-8 7 1.6-4.1A8.5 8.5 0 1 1 12 20.5H4.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <h3 className="mt-5 text-center text-2xl font-bold tracking-tight text-slate-900">How can we help?</h3>
                      <p className="mx-auto mt-2 max-w-lg text-center text-sm leading-6 text-slate-500">Ask a common study question and the assistant can answer. If it can’t help, your question will be sent to your coordinator.</p>
                      <div className="mt-6 grid gap-2 sm:grid-cols-3">
                        {FAQ_STARTER_QUESTIONS.map((question) => (
                          <button className="rounded-xl border border-slate-200 bg-white p-3 text-left text-xs font-medium leading-5 text-slate-700 shadow-sm transition hover:border-teal-300 hover:bg-teal-50/50 hover:text-teal-900 disabled:opacity-50 sm:text-sm" disabled={faqLoading} key={question} onClick={() => void sendChatQuestion(question)} type="button">
                            {question}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mx-auto grid max-w-3xl gap-5">
                      {chatItems.map((item) => item.kind === 'message' ? (
                        <article className={`max-w-[90%] rounded-2xl p-4 ${item.message.sender === 'patient' ? 'ml-auto bg-teal-700 text-white shadow-sm' : 'border border-slate-100 bg-white shadow-sm'}`} key={`message-${item.message.id}`}>
                          <p className={`mb-1 text-xs font-semibold ${item.message.sender === 'patient' ? 'text-teal-100' : 'text-slate-500'}`}>{item.message.sender === 'patient' ? 'You · Sent to coordinator' : 'Study coordinator'}</p>
                          <p className="whitespace-pre-wrap break-words text-sm">{item.message.body}</p>
                          <time className={`mt-2 block text-right text-[11px] ${item.message.sender === 'patient' ? 'text-teal-100' : 'text-slate-400'}`} dateTime={item.message.created_at}>
                            {new Date(item.message.created_at).toLocaleString()}
                          </time>
                        </article>
                      ) : (
                        <article className="grid gap-3" key={`assistant-${item.turn.id}`}>
                          <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-teal-700 px-4 py-3 text-sm leading-6 text-white shadow-sm sm:max-w-[80%]">
                            <p className="whitespace-pre-wrap">{item.turn.question}</p>
                          </div>
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-teal-50 text-teal-700" aria-hidden="true">
                              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                                <path d="M12 3.5v17M3.5 12h17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                                <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" />
                              </svg>
                            </div>
                            <div className="min-w-0 max-w-[90%] text-sm leading-6 text-slate-700 sm:max-w-[85%]">
                              <p className="mb-1 text-xs font-semibold text-slate-500">Study assistant</p>
                              <p className="whitespace-pre-wrap">{item.turn.answer.answer}</p>
                            </div>
                          </div>
                        </article>
                      ))}
                      {chatNotice && <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="status">{chatNotice}</p>}
                    </div>
                  )}
                  {faqLoading && <p className="mx-auto mt-4 max-w-3xl text-sm text-slate-500" role="status">Checking your question…</p>}
                  {error && <p className="mx-auto mt-4 max-w-3xl rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p>}
                  <div ref={faqConversationEndRef} />
                </div>

                <div className="border-t border-slate-100 bg-white px-4 py-4 sm:px-6">
                  <form className="mx-auto max-w-3xl" onSubmit={sendMessage}>
                    <label className="sr-only" htmlFor="messages-chat-input">Ask a question or message your coordinator</label>
                    <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-teal-400 focus-within:ring-4 focus-within:ring-teal-500/10">
                      <textarea className="max-h-32 min-h-11 flex-1 resize-y border-0 bg-transparent px-3 py-2.5 text-sm leading-5 text-slate-800 outline-none placeholder:text-slate-400 focus:ring-0" disabled={faqLoading} id="messages-chat-input" maxLength={1000} onChange={(event) => setMessageDraft(event.target.value)} placeholder="Ask a question about your study..." required rows={1} value={messageDraft} />
                      <button aria-label="Send question" className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-700 text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300" disabled={faqLoading || !messageDraft.trim()} type="submit">
                        {faqLoading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : (
                          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
                            <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </button>
                    </div>
                    <p className="mt-2 text-center text-[11px] leading-4 text-slate-400">Common questions may be answered by AI; questions it can’t answer go to your coordinator. Don’t include sensitive health information or emergencies.</p>
                  </form>
                </div>
              </section>
            ) : section === 'faq' ? (
              <section className="flex h-[min(76vh,820px)] min-h-[560px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" aria-label="Study FAQ chat">
                <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-4 sm:px-6">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-teal-600 to-cyan-700 text-white shadow-sm" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
                        <path d="M12 3.5v17M3.5 12h17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                        <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" opacity=".75" />
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <h2 className="truncate text-base font-bold text-slate-900 sm:text-lg">Study FAQ assistant</h2>
                      <p className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        Local assistant · Replies are not medical advice
                      </p>
                    </div>
                  </div>
                  <button
                    className="shrink-0 rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 disabled:opacity-40 sm:text-sm"
                    disabled={faqConversation.length === 0 || faqLoading}
                    onClick={() => setFaqConversation([])}
                    type="button"
                  >
                    New chat
                  </button>
                </header>

                <div className="flex-1 overflow-y-auto bg-[#fbfcfd] px-4 py-5 sm:px-8 sm:py-7" role="log" aria-label="FAQ conversation" aria-live="polite">
                  {faqConversation.length === 0 ? (
                    <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center">
                      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-teal-50 text-teal-700">
                        <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden="true">
                          <path d="M7.5 9h9m-9 4h5m-8 7 1.6-4.1A8.5 8.5 0 1 1 12 20.5H4.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </div>
                      <h3 className="mt-5 text-center text-2xl font-bold tracking-tight text-slate-900">What can I help you find?</h3>
                      <p className="mx-auto mt-2 max-w-lg text-center text-sm leading-6 text-slate-500">
                        Ask about study participation, appointments, account access, privacy, or general health terms.
                      </p>
                      <div className="mt-6 grid gap-2 sm:grid-cols-3">
                        {FAQ_STARTER_QUESTIONS.map((question) => (
                          <button
                            className="rounded-xl border border-slate-200 bg-white p-3 text-left text-xs font-medium leading-5 text-slate-700 shadow-sm transition hover:border-teal-300 hover:bg-teal-50/50 hover:text-teal-900 disabled:opacity-50 sm:text-sm"
                            disabled={faqLoading}
                            key={question}
                            onClick={() => void sendChatQuestion(question)}
                            type="button"
                          >
                            {question}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mx-auto grid max-w-3xl gap-6">
                      {faqConversation.map((turn) => (
                        <article className="grid gap-4" key={turn.id}>
                          <div className="ml-auto max-w-[90%] rounded-2xl rounded-br-md bg-teal-700 px-4 py-3 text-sm leading-6 text-white shadow-sm sm:max-w-[80%]">
                            <p className="whitespace-pre-wrap">{turn.question}</p>
                          </div>
                          {turn.answer && (
                            <div className="flex items-start gap-3">
                              <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-teal-50 text-teal-700" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                                  <path d="M12 3.5v17M3.5 12h17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                                  <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.5" />
                                </svg>
                              </div>
                              <div className="min-w-0 max-w-[90%] text-sm leading-6 text-slate-700 sm:max-w-[85%]">
                                <p className="mb-1 text-xs font-semibold text-slate-500">Study FAQ assistant</p>
                                <p className="whitespace-pre-wrap">{turn.answer.answer}</p>
                                {turn.answer.sources.length > 0 && (
                                  <div className="mt-3 border-t border-slate-200 pt-3">
                                    <h3 className="text-xs font-semibold text-slate-600">Sources</h3>
                                    <ul className="mt-1 grid gap-1">
                                      {turn.answer.sources.map((source) => (
                                        <li key={source.url}>
                                          <a className="break-all text-teal-800 underline underline-offset-2" href={source.url} rel="noopener noreferrer" target="_blank">
                                            {source.title}
                                          </a>
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                          {turn.error && <p className="ml-11 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{turn.error}</p>}
                        </article>
                      ))}
                      {faqLoading && (
                        <div className="flex items-center gap-3" role="status">
                          <div className="grid h-8 w-8 place-items-center rounded-lg bg-teal-50 text-teal-700" aria-hidden="true">
                            <span className="h-2 w-2 animate-pulse rounded-full bg-teal-600" />
                          </div>
                          <p className="text-sm text-slate-500">Checking the approved information…</p>
                        </div>
                      )}
                      <div ref={faqConversationEndRef} />
                    </div>
                  )}
                </div>

                <div className="border-t border-slate-100 bg-white px-4 py-4 sm:px-6">
                  <form className="mx-auto max-w-3xl" onSubmit={sendMessage}>
                    <label className="sr-only" htmlFor="faq-chat-input">Ask a question</label>
                    <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-sm transition focus-within:border-teal-400 focus-within:ring-4 focus-within:ring-teal-500/10">
                      <textarea
                        className="max-h-32 min-h-11 flex-1 resize-y border-0 bg-transparent px-3 py-2.5 text-sm leading-5 text-slate-800 outline-none placeholder:text-slate-400 focus:ring-0"
                        disabled={faqLoading}
                        id="faq-chat-input"
                        maxLength={1000}
                        onChange={(event) => setMessageDraft(event.target.value)}
                        placeholder="Ask a study or general information question..."
                        required
                        rows={1}
                        value={messageDraft}
                      />
                      <button
                        aria-label="Send question"
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-teal-700 text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                        disabled={faqLoading || !messageDraft.trim()}
                        type="submit"
                      >
                        {faqLoading ? (
                          <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                        ) : (
                          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
                            <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                      </button>
                    </div>
                    <p className="mt-2 text-center text-[11px] leading-4 text-slate-400">
                      General information only. Don’t include names, personal health details, or urgent concerns.
                    </p>
                  </form>
                </div>
              </section>
            ) : section === 'notifications' ? (
              <section className="mt-2" aria-label="Notifications">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-2xl font-bold tracking-tight text-slate-900">Notifications</h2>
                    <p className="mt-1 text-sm text-slate-600">Unread coordinator messages and appointment updates. This list refreshes automatically while you’re signed in.</p>
                  </div>
                </div>
                {loadingNotifications && appointmentNotifications.length === 0 && unreadMessages.length === 0 ? (
                  <p className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 p-6 text-sm text-slate-600">Loading notifications...</p>
                ) : unreadMessages.length + appointmentNotifications.length === 0 ? (
                  <p className="mt-5 rounded-2xl border border-slate-100 bg-slate-50 p-6 text-sm text-slate-600">You’re all caught up.</p>
                ) : (
                  <ul className="mt-4 divide-y divide-slate-100 rounded-2xl border border-slate-200">
                    {appointmentNotifications.map((notification) => (
                      <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between" key={notification.id}>
                        <div>
                          <p className="font-semibold text-teal-900">{notification.title}</p>
                          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{notification.body}</p>
                          <time className="mt-2 block text-xs text-slate-500" dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString()}</time>
                        </div>
                        <button
                          className="shrink-0 self-start rounded-xl border border-teal-200 px-4 py-2.5 text-sm font-semibold text-teal-800 transition-colors hover:bg-teal-50"
                          onClick={() => void markAppointmentNotificationRead(notification.id)}
                          type="button"
                        >
                          Mark as read
                        </button>
                      </li>
                    ))}
                    {unreadMessages.map((message) => (
                      <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between" key={message.id}>
                        <div>
                          <p className="font-semibold">New message from your coordinator</p>
                          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{message.body}</p>
                          <time className="mt-2 block text-xs text-slate-500" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
                        </div>
                        <button
                          className="shrink-0 self-start rounded-xl bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-teal-800"
                          onClick={() => { setSection('messages'); setMessageToast(''); void loadMessages(); }}
                          type="button"
                        >
                          Open conversation
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            ) : section === 'settings' ? (
              <section className="mt-2" aria-label="Notification settings">
                <h2 className="text-2xl font-bold tracking-tight text-slate-900">Settings</h2>
                <p className="mt-1 text-sm text-slate-600">Choose how this browser shows new-message alerts.</p>
                <label className="mt-5 flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
                  <input
                    checked={toastEnabled}
                    className="mt-1 h-4 w-4 accent-teal-700"
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      setToastEnabled(enabled);
                      localStorage.setItem(TOAST_PREFERENCE_KEY, String(enabled));
                      if (!enabled) setMessageToast('');
                    }}
                    type="checkbox"
                  />
                  <span>
                    <span className="block font-semibold">In-app message pop-ups</span>
                    <span className="mt-1 block text-sm text-slate-600">Show a toast when a new message arrives. Unread counts and the Notifications page remain available when this is off.</span>
                  </span>
                </label>
              </section>
            ) : (
              <section className="mt-2" aria-label="About Clinical Connect AI">
                <h2 className="text-2xl font-bold tracking-tight text-slate-900">About</h2>
                <p className="mt-3 text-slate-700">Clinical Connect AI is a synthetic-data demonstration portal for patient-coordinator messages, appointment information, and study FAQs.</p>
                <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">Demonstration only. Do not enter real patient information. This portal does not provide medical advice.</p>
              </section>
            )}
            </div>
          </section>
        ) : (
          <section className="grid overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-900/5 md:min-h-[640px] md:grid-cols-[0.9fr_1.1fr]">
            <aside className="relative hidden overflow-hidden bg-gradient-to-br from-[#0f3c49] via-[#115e66] to-[#087e78] p-8 text-white md:flex md:flex-col md:justify-between lg:p-10 xl:p-14">
              <div className="pointer-events-none absolute -right-24 -top-20 h-72 w-72 rounded-full border border-white/10" />
              <div className="pointer-events-none absolute -right-8 -top-4 h-40 w-40 rounded-full border border-white/10" />
              <div className="pointer-events-none absolute -bottom-28 -left-20 h-72 w-72 rounded-full bg-cyan-300/10 blur-2xl" />
              <div className="relative">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-semibold tracking-wide text-teal-50">
                  <span className="h-2 w-2 rounded-full bg-emerald-300" />
                  YOUR PATIENT PORTAL
                </span>
                <h2 className="mt-10 max-w-sm text-4xl font-bold leading-tight tracking-tight xl:text-5xl">Stay connected throughout your study.</h2>
                <p className="mt-5 max-w-sm text-base leading-7 text-teal-50/85">A simple, secure place to keep in touch with your study coordinator and stay up to date.</p>
              </div>
              <div className="relative mt-12 grid gap-4">
                {[
                  ['01', 'Message your coordinator', 'Keep study questions in one convenient place.'],
                  ['02', 'Stay up to date', 'See appointment information and new notifications.'],
                  ['03', 'Find helpful information', 'Browse study FAQs and general information.'],
                ].map(([number, title, description]) => (
                  <div className="flex gap-4 rounded-2xl border border-white/15 bg-white/[0.08] p-4 backdrop-blur-sm" key={number}>
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/15 text-xs font-bold text-white">{number}</span>
                    <div>
                      <p className="text-sm font-semibold text-white">{title}</p>
                      <p className="mt-1 text-xs leading-5 text-teal-50/75">{description}</p>
                    </div>
                  </div>
                ))}
              </div>
              <p className="relative mt-10 text-xs leading-5 text-teal-50/65">A demonstration portal. Do not enter real patient information.</p>
            </aside>
            <div className="flex flex-col justify-center p-6 sm:p-10 lg:px-12 xl:px-16">
            <div className="mb-2 inline-flex w-fit items-center gap-2 rounded-full bg-teal-50 px-3 py-1.5 text-xs font-semibold text-teal-800 md:hidden">
              <span className="h-2 w-2 rounded-full bg-teal-600" />
              Patient portal
            </div>
            <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
              {mode === 'login' ? 'Log in' : 'Create your patient account'}
            </h1>
            <p className="mt-3 max-w-md text-sm leading-6 text-slate-500 sm:text-base">
              {mode === 'login'
                ? 'Log in with your email and password, or create an account if this is your first visit.'
                : 'Use the email on your patient record to create your account. New patients can enter their name below.'}
            </p>

            <div className="mt-7 grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
              {([['login', 'Log in'], ['signup', 'Sign up']] as const).map(([value, label]) => (
                <button
                  aria-pressed={mode === value}
                  className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${mode === value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
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
                  <label className="grid gap-2 text-sm font-semibold text-slate-700">
                    Given name (for new patients)
                      <input autoComplete="given-name" className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 font-normal shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-500/10" maxLength={128} onChange={(event) => setGivenName(event.target.value)} value={givenName} />
                  </label>
                  <label className="grid gap-2 text-sm font-semibold text-slate-700">
                    Family name (for new patients)
                      <input autoComplete="family-name" className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 font-normal shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-500/10" maxLength={128} onChange={(event) => setFamilyName(event.target.value)} value={familyName} />
                  </label>
                </>
              )}
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                Email address <span className="text-teal-700">(required)</span>
                <input autoComplete="email" className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 font-normal shadow-sm outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-500/10" maxLength={255} onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
                {mode === 'signup' && (
                  <span className="text-xs font-normal text-slate-500">
                    We use this email to find your existing patient record. If no record matches, enter your name above to create one.
                  </span>
                )}
              </label>
              <label className="grid gap-2 text-sm font-semibold text-slate-700">
                Password
                <input
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  className="rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-3 font-normal shadow-sm outline-none transition focus:border-teal-500 focus:bg-white focus:ring-4 focus:ring-teal-500/10"
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
              <button className="mt-1 rounded-xl bg-teal-700 px-5 py-3 font-semibold text-white shadow-md shadow-teal-900/15 transition hover:bg-teal-800 focus:outline-none focus:ring-4 focus:ring-teal-700/20 disabled:cursor-wait disabled:opacity-60" disabled={loading} type="submit">
                {loading ? 'Please wait...' : mode === 'login' ? 'Log in' : 'Sign up'}
              </button>
            </form>
            <div className="mt-7 flex items-start gap-3 rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-500">
              <svg viewBox="0 0 24 24" fill="none" className="mt-0.5 h-4 w-4 shrink-0 text-teal-700" aria-hidden="true">
                <path d="M7 10V7a5 5 0 0 1 10 0v3m-11 0h12a2 2 0 0 1 2 2v8H4v-8a2 2 0 0 1 2-2Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>Your account is protected. This demonstration uses synthetic data only; never enter real patient information.</span>
            </div>
            </div>
          </section>
        )}

        {patient && (
          <p className="mt-6 text-center text-xs text-slate-400">
            Clinical Connect AI · Synthetic demonstration only
          </p>
        )}
      </div>
    </main>
  );
}
