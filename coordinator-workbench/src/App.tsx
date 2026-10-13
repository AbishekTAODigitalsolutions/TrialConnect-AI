import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
  read_at: string | null;
};

type CoordinatorUnreadMessage = {
  id: string;
  patient_id: string;
  patient_given_name: string;
  patient_family_name: string;
  body: string;
  created_at: string;
};

type WorkbenchSection = 'patients' | 'notifications' | 'settings' | 'activity' | 'about';
const TOAST_PREFERENCE_KEY = 'clinical-connect-coordinator-toast-enabled';
const STAFF_TOKEN_KEY = 'clinical-connect-staff-token';

type Coordinator = {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'coordinator';
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

type CoordinatorActivity = {
  id: string;
  coordinator_id: string | null;
  full_name: string | null;
  email: string | null;
  event_type: 'login' | 'login_failed' | 'logout' | 'message_read';
  patient_id: string | null;
  message_id: string | null;
  details: Record<string, string> | null;
  created_at: string;
};

type CoordinatorAccessRequest = {
  id: string;
  email: string;
  full_name: string;
  status: 'pending';
  notification_status: 'sent' | 'failed' | 'not_configured' | 'pending';
  notification_error: string | null;
  created_at: string;
};

type Appointment = {
  id: string;
  patient_id: string;
  title: string;
  location: string | null;
  starts_at: string;
  status: 'scheduled' | 'cancelled';
  email_deliveries: AppointmentEmailDelivery[];
};

type AppointmentEmailDelivery = {
  id: string;
  email_type: 'confirmation' | 'reminder_24_hours';
  scheduled_for: string;
  status: 'pending' | 'sending' | 'sent' | 'failed';
  attempts: number;
  last_attempt_at: string | null;
  sent_at: string | null;
  last_error: string | null;
  smtp_configured: boolean;
};

export default function App() {
  const [section, setSection] = useState<WorkbenchSection>('patients');
  const [token, setToken] = useState(() => sessionStorage.getItem(STAFF_TOKEN_KEY));
  const [staff, setStaff] = useState<Coordinator | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [accessRequestOpen, setAccessRequestOpen] = useState(false);
  const [accessRequestName, setAccessRequestName] = useState('');
  const [accessRequestEmail, setAccessRequestEmail] = useState('');
  const [accessRequestPassword, setAccessRequestPassword] = useState('');
  const [accessRequestFeedback, setAccessRequestFeedback] = useState('');
  const [team, setTeam] = useState<Coordinator[]>([]);
  const [accessRequests, setAccessRequests] = useState<CoordinatorAccessRequest[]>([]);
  const [activity, setActivity] = useState<CoordinatorActivity[]>([]);
  const [newStaffName, setNewStaffName] = useState('');
  const [newStaffEmail, setNewStaffEmail] = useState('');
  const [newStaffPassword, setNewStaffPassword] = useState('');
  const [newStaffRole, setNewStaffRole] = useState<'admin' | 'coordinator'>('coordinator');
  const [toastEnabled, setToastEnabled] = useState(
    () => localStorage.getItem(TOAST_PREFERENCE_KEY) !== 'false',
  );
  const [patients, setPatients] = useState<Patient[]>([]);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [unreadMessages, setUnreadMessages] = useState<CoordinatorUnreadMessage[]>([]);
  const [notificationToast, setNotificationToast] = useState<CoordinatorUnreadMessage | null>(null);
  const seenUnreadMessageIds = useRef(new Set<string>());
  const locallyReadMessageIds = useRef(new Set<string>());
  const unreadRequestId = useRef(0);
  const initializedUnreadMessages = useRef(false);
  const [replyDraft, setReplyDraft] = useState('');
  const [appointmentPatient, setAppointmentPatient] = useState<Patient | null>(null);
  const [appointmentTitle, setAppointmentTitle] = useState('Doctor appointment');
  const [appointmentLocation, setAppointmentLocation] = useState('');
  const [appointmentTime, setAppointmentTime] = useState('');
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const authorizedFetch = useCallback((url: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    return fetch(url, { ...init, headers }).then((response) => {
      if (response.status === 401 && token) {
        sessionStorage.removeItem(STAFF_TOKEN_KEY);
        setToken(null);
        setStaff(null);
        setPatients([]);
        setSelectedPatient(null);
        setConversation([]);
        setUnreadMessages([]);
        setNotificationToast(null);
        setAppointmentPatient(null);
        setAppointments([]);
        setError('Your staff session has expired. Please sign in again.');
      }
      return response;
    });
  }, [token]);

  useEffect(() => {
    let mounted = true;
    const verifySession = async () => {
      if (!token) {
        setAuthChecking(false);
        return;
      }
      try {
        const response = await fetch(`${CORE_API_URL}/coordinator-auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!response.ok) throw new Error('Staff session expired.');
        const account: Coordinator = await response.json();
        if (mounted) setStaff(account);
      } catch {
        sessionStorage.removeItem(STAFF_TOKEN_KEY);
        if (mounted) {
          setToken(null);
          setStaff(null);
        }
      } finally {
        if (mounted) setAuthChecking(false);
      }
    };
    void verifySession();
    return () => { mounted = false; };
  }, []);

  const signIn = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    try {
      const response = await fetch(`${CORE_API_URL}/coordinator-auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not sign in.');
      sessionStorage.setItem(STAFF_TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setStaff(data.coordinator);
      setLoginPassword('');
      setSection('patients');
      setLoading(true);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Could not sign in.');
    }
  };

  const submitAccessRequest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setAccessRequestFeedback('');
    try {
      const response = await fetch(`${CORE_API_URL}/coordinator-auth/access-requests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: accessRequestName,
          email: accessRequestEmail,
          password: accessRequestPassword,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not submit the access request.');
      setAccessRequestName('');
      setAccessRequestEmail('');
      setAccessRequestPassword('');
      setAccessRequestOpen(false);
      setAccessRequestFeedback(data.message);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Could not submit the access request.');
    }
  };

  const signOut = () => {
    void authorizedFetch(`${CORE_API_URL}/coordinator-auth/logout`, { method: 'POST' });
    sessionStorage.removeItem(STAFF_TOKEN_KEY);
    setToken(null);
    setStaff(null);
    setPatients([]);
    setUnreadMessages([]);
    setSelectedPatient(null);
    setConversation([]);
    setNotificationToast(null);
    setAppointmentPatient(null);
    setAppointments([]);
    setTeam([]);
    setAccessRequests([]);
    setActivity([]);
    setSection('patients');
  };

  const loadWorkbench = useCallback(async () => {
    if (!staff) return;
    setError('');
    try {
      const patientsResponse = await authorizedFetch(`${CORE_API_URL}/patients?limit=100`);
      if (!patientsResponse.ok) {
        throw new Error('The core service returned an error while loading patients.');
      }
      const patientData: Patient[] = await patientsResponse.json();
      setPatients(patientData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Could not load patients.');
    } finally {
      setLoading(false);
    }
  }, [authorizedFetch, staff]);

  useEffect(() => {
    if (staff) void loadWorkbench();
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
        ? await authorizedFetch(`${CORE_API_URL}/patients/${patient.id}`, { method: 'DELETE' })
        : await authorizedFetch(`${CORE_API_URL}/patients/${patient.id}`, {
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

  const openConversation = async (patient: Patient) => {
    setSelectedPatient(patient);
    setConversation([]);
    setError('');
    try {
      const response = await authorizedFetch(`${CORE_API_URL}/coordinator/patients/${patient.id}/messages`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not load the conversation.');
      setConversation(data);
      const incomingIds = unreadMessages
        .filter((message) => message.patient_id === patient.id)
        .map((message) => message.id);
      if (incomingIds.length > 0) {
        const readResponse = await authorizedFetch(`${CORE_API_URL}/coordinator/patients/${patient.id}/messages/read`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message_ids: incomingIds }),
        });
        if (!readResponse.ok) {
          const readData = await readResponse.json();
          throw new Error(readData.detail ?? 'Could not mark messages as read.');
        }
        incomingIds.forEach((messageId) => locallyReadMessageIds.current.add(messageId));
        unreadRequestId.current += 1;
        setUnreadMessages((current) => current.filter((message) => !incomingIds.includes(message.id)));
        setNotificationToast((current) => (
          current && incomingIds.includes(current.id) ? null : current
        ));
      }
    } catch (conversationError) {
      setError(conversationError instanceof Error ? conversationError.message : 'Could not load the conversation.');
    }
  };

  const loadUnreadMessages = useCallback(async () => {
    if (!staff) return;
    const requestId = ++unreadRequestId.current;
    try {
      const response = await authorizedFetch(`${CORE_API_URL}/coordinator/messages/unread`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not check for new messages.');
      if (requestId !== unreadRequestId.current) return;
      const unread: CoordinatorUnreadMessage[] = data.filter(
        (message: CoordinatorUnreadMessage) => !locallyReadMessageIds.current.has(message.id),
      );
      if (initializedUnreadMessages.current) {
        const newMessage = unread.find((message) => !seenUnreadMessageIds.current.has(message.id));
        if (newMessage && toastEnabled) setNotificationToast(newMessage);
      }
      unread.forEach((message) => seenUnreadMessageIds.current.add(message.id));
      initializedUnreadMessages.current = true;
      setUnreadMessages(unread);
    } catch (notificationError) {
      setError(notificationError instanceof Error ? notificationError.message : 'Could not check for new messages.');
    }
  }, [authorizedFetch, staff, toastEnabled]);

  useEffect(() => {
    locallyReadMessageIds.current.clear();
    seenUnreadMessageIds.current.clear();
    unreadRequestId.current += 1;
    initializedUnreadMessages.current = false;
    if (!staff) setUnreadMessages([]);
  }, [staff?.id]);

  useEffect(() => {
    if (!staff) return;
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
  }, [loadUnreadMessages, staff]);

  const sendCoordinatorReply = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedPatient) return;
    setUpdatingId(selectedPatient.id);
    setError('');
    try {
      const response = await authorizedFetch(`${CORE_API_URL}/coordinator/patients/${selectedPatient.id}/messages`, {
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
      const response = await authorizedFetch(`${CORE_API_URL}/coordinator/patients/${patient.id}/appointments`);
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
      const response = await authorizedFetch(
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

  const loadAdminData = useCallback(async () => {
    if (staff?.role !== 'admin') return;
    setError('');
    try {
      const [teamResponse, requestsResponse, activityResponse] = await Promise.all([
        authorizedFetch(`${CORE_API_URL}/coordinator-auth/team`),
        authorizedFetch(`${CORE_API_URL}/coordinator-auth/access-requests`),
        authorizedFetch(`${CORE_API_URL}/coordinator-auth/activity?limit=200`),
      ]);
      const teamData = await teamResponse.json();
      const requestsData = await requestsResponse.json();
      const activityData = await activityResponse.json();
      if (!teamResponse.ok) throw new Error(teamData.detail ?? 'Could not load staff accounts.');
      if (!requestsResponse.ok) throw new Error(requestsData.detail ?? 'Could not load access requests.');
      if (!activityResponse.ok) throw new Error(activityData.detail ?? 'Could not load staff activity.');
      setTeam(teamData);
      setAccessRequests(requestsData);
      setActivity(activityData);
    } catch (adminError) {
      setError(adminError instanceof Error ? adminError.message : 'Could not load administrator data.');
    }
  }, [authorizedFetch, staff]);

  useEffect(() => {
    if (staff?.role === 'admin' && (section === 'settings' || section === 'activity')) {
      void loadAdminData();
    }
  }, [loadAdminData, section, staff]);

  useEffect(() => {
    if (staff?.role !== 'admin' || section !== 'settings') return;
    const intervalId = window.setInterval(() => void loadAdminData(), 15_000);
    return () => window.clearInterval(intervalId);
  }, [loadAdminData, section, staff]);

  const decideAccessRequest = async (
    request: CoordinatorAccessRequest,
    decision: 'approve' | 'reject',
  ) => {
    setError('');
    try {
      const response = await authorizedFetch(
        `${CORE_API_URL}/coordinator-auth/access-requests/${request.id}/decision`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision }),
        },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not review this access request.');
      await loadAdminData();
    } catch (decisionError) {
      setError(decisionError instanceof Error ? decisionError.message : 'Could not review this access request.');
    }
  };

  const retryAccessRequestEmail = async (request: CoordinatorAccessRequest) => {
    setError('');
    try {
      const response = await authorizedFetch(
        `${CORE_API_URL}/coordinator-auth/access-requests/${request.id}/notify`,
        { method: 'POST' },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not resend the admin notification.');
      await loadAdminData();
    } catch (notifyError) {
      setError(notifyError instanceof Error ? notifyError.message : 'Could not resend the admin notification.');
    }
  };

  const createCoordinator = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    try {
      const response = await authorizedFetch(`${CORE_API_URL}/coordinator-auth/team`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: newStaffName,
          email: newStaffEmail,
          password: newStaffPassword,
          role: newStaffRole,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not create the coordinator account.');
      setNewStaffName('');
      setNewStaffEmail('');
      setNewStaffPassword('');
      setNewStaffRole('coordinator');
      await loadAdminData();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Could not create the coordinator account.');
    }
  };

  const toggleCoordinator = async (account: Coordinator) => {
    setError('');
    try {
      const response = await authorizedFetch(
        `${CORE_API_URL}/coordinator-auth/team/${account.id}?is_active=${!account.is_active}`,
        { method: 'PATCH' },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? 'Could not update the staff account.');
      await loadAdminData();
    } catch (accountError) {
      setError(accountError instanceof Error ? accountError.message : 'Could not update the staff account.');
    }
  };

  if (authChecking) {
    return <main className="min-h-screen bg-slate-900 p-8 text-slate-200">Checking staff session...</main>;
  }

  if (!staff) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-900 p-5 text-slate-50">
        <section className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-800 p-7 shadow-xl">
          <p className="text-sm font-semibold uppercase tracking-[0.15em] text-cyan-300">Clinical Connect AI</p>
          <h1 className="mt-3 text-2xl font-bold">Coordinator sign in</h1>
          <p className="mt-2 text-sm text-slate-400">Use the staff account provided by your administrator.</p>
          {error && <p role="alert" className="mt-4 rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
          {accessRequestFeedback && <p role="status" className="mt-4 rounded-lg bg-green-950 p-3 text-sm text-green-200">{accessRequestFeedback}</p>}
          {!accessRequestOpen ? (
            <>
          <form onSubmit={signIn}>
          <label className="mt-5 block text-sm font-medium text-slate-300">
            Email
            <input autoComplete="username" className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" onChange={(event) => setLoginEmail(event.target.value)} required type="email" value={loginEmail} />
          </label>
          <label className="mt-4 block text-sm font-medium text-slate-300">
            Password
            <input autoComplete="current-password" className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" onChange={(event) => setLoginPassword(event.target.value)} required type="password" value={loginPassword} />
          </label>
          <button className="mt-5 w-full rounded-lg bg-cyan-700 px-4 py-2.5 font-semibold text-white hover:bg-cyan-600" type="submit">Sign in</button>
          <p className="mt-4 text-xs text-slate-500">If no admin account exists yet, configure the bootstrap admin in the local API environment settings.</p>
          </form>
              <button className="mt-4 w-full rounded-lg border border-slate-600 px-4 py-2.5 text-sm font-semibold text-cyan-200 hover:bg-slate-700" onClick={() => { setAccessRequestOpen(true); setError(''); }} type="button">
                Request coordinator access
              </button>
            </>
          ) : (
            <>
              <h2 className="mt-5 text-lg font-semibold">Request coordinator access</h2>
              <p className="mt-1 text-sm text-slate-400">An administrator must approve your request before you can sign in.</p>
              <form className="mt-4" onSubmit={submitAccessRequest}>
                <label className="mt-3 block text-sm font-medium text-slate-300">
                  Full name
                  <input autoComplete="name" className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" maxLength={255} onChange={(event) => setAccessRequestName(event.target.value)} required value={accessRequestName} />
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-300">
                  Work email
                  <input autoComplete="email" className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" maxLength={255} onChange={(event) => setAccessRequestEmail(event.target.value)} required type="email" value={accessRequestEmail} />
                </label>
                <label className="mt-3 block text-sm font-medium text-slate-300">
                  Password
                  <input autoComplete="new-password" className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-white" minLength={12} onChange={(event) => setAccessRequestPassword(event.target.value)} required type="password" value={accessRequestPassword} />
                </label>
                <button className="mt-5 w-full rounded-lg bg-cyan-700 px-4 py-2.5 font-semibold text-white hover:bg-cyan-600" type="submit">Submit for admin approval</button>
              </form>
              <button className="mt-3 w-full rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700" onClick={() => { setAccessRequestOpen(false); setError(''); }} type="button">
                Back to sign in
              </button>
            </>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-900 p-5 text-slate-50 sm:p-8">
      <div className="mx-auto max-w-6xl rounded-2xl border border-slate-700 bg-slate-800 p-6 shadow-xl sm:p-8">
        <div className="flex flex-col gap-6 md:flex-row">
          <aside className="rounded-xl border border-slate-700 bg-slate-900 p-4 md:w-56 md:shrink-0">
            <p className="text-sm font-semibold uppercase tracking-[0.15em] text-cyan-300">Clinical Connect AI</p>
            <p className="mt-1 text-xs text-slate-400">Coordinator Workbench</p>
            <p className="mt-4 truncate text-xs font-medium text-slate-200" title={staff.email}>{staff.full_name}</p>
            <p className="text-[11px] uppercase tracking-wide text-cyan-300">{staff.role}</p>
            <nav aria-label="Coordinator workbench navigation" className="mt-5 grid gap-1">
              {([
                ['patients', 'Patients'],
                ['notifications', 'Notifications'],
                ['settings', 'Settings'],
                ...(staff.role === 'admin' ? [['activity', 'Staff activity'] as const] : []),
                ['about', 'About'],
              ] as const).map(([value, label]) => (
                <button
                  aria-current={section === value ? 'page' : undefined}
                  className={`flex items-center justify-between rounded-lg px-3 py-2 text-left text-sm font-semibold ${
                    section === value ? 'bg-cyan-800 text-white' : 'text-slate-300 hover:bg-slate-800'
                  }`}
                  key={value}
                  onClick={() => setSection(value)}
                  type="button"
                >
                  <span>{label}</span>
                  {value === 'notifications' && unreadMessages.length > 0 && (
                    <span className={`rounded-full px-2 py-0.5 text-xs ${
                      section === value ? 'bg-white text-cyan-900' : 'bg-cyan-900 text-cyan-100'
                    }`}>{unreadMessages.length}</span>
                  )}
                </button>
              ))}
            </nav>
            <button className="mt-4 w-full rounded-lg border border-slate-700 px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800" onClick={signOut} type="button">
              Sign out
            </button>
          </aside>
          <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">Coordinator Workbench</p>
        <p className="mt-3 text-sm font-semibold text-slate-400">Clinical Connect AI</p>
        {section === 'patients' && (
          <>
        <h1 className="mt-3 text-3xl font-bold">Patient management</h1>
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
        {notificationToast && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-cyan-700 bg-cyan-950 p-3 text-sm text-cyan-100" role="status">
            <span>New message from {notificationToast.patient_given_name} {notificationToast.patient_family_name}.</span>
            <div className="flex shrink-0 gap-3">
              {patients.find((patient) => patient.id === notificationToast.patient_id) && (
                <button
                  className="font-semibold underline"
                  onClick={() => {
                    const patient = patients.find((item) => item.id === notificationToast.patient_id);
                    setNotificationToast(null);
                    if (patient) void openConversation(patient);
                  }}
                  type="button"
                >
                  Open message
                </button>
              )}
              <button className="font-semibold" onClick={() => setNotificationToast(null)} type="button" aria-label="Dismiss notification">
                Dismiss
              </button>
            </div>
          </div>
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
                      Messages{unreadMessages.filter((message) => message.patient_id === patient.id).length > 0
                        ? ` (${unreadMessages.filter((message) => message.patient_id === patient.id).length})`
                        : ''}
                    </button>
                    <button
                      className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold hover:bg-slate-700"
                      onClick={() => void loadAppointments(patient)}
                      type="button"
                    >
                      Appointments
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
          </>
        )}
        {section === 'notifications' && (
          <section className="mt-5" aria-label="Notifications">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h1 className="text-3xl font-bold">Notifications</h1>
                <p className="mt-1 text-sm text-slate-400">Unread messages from patients. This list updates automatically while you’re signed in.</p>
              </div>
            </div>
            {unreadMessages.length === 0 ? (
              <p className="mt-5 rounded-lg bg-slate-900 p-4 text-sm text-slate-400">You’re all caught up.</p>
            ) : (
              <ul className="mt-4 divide-y divide-slate-700 rounded-xl border border-slate-700">
                {unreadMessages.map((message) => (
                  <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between" key={message.id}>
                    <div>
                      <p className="font-semibold">{message.patient_given_name} {message.patient_family_name}</p>
                      <p className="mt-1 whitespace-pre-wrap text-sm text-slate-300">{message.body}</p>
                      <time className="mt-2 block text-xs text-slate-400" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time>
                    </div>
                    {patients.find((patient) => patient.id === message.patient_id) && (
                      <button
                        className="shrink-0 self-start rounded-lg bg-cyan-800 px-3 py-2 text-sm font-semibold text-white"
                        onClick={() => {
                          const patient = patients.find((item) => item.id === message.patient_id);
                          if (patient) void openConversation(patient);
                        }}
                        type="button"
                      >
                        Open conversation
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
        {section === 'settings' && (
          <section className="mt-5" aria-label="Settings">
            <h1 className="text-3xl font-bold">Settings</h1>
            <p className="mt-1 text-sm text-slate-400">Choose how this browser shows new-message alerts.</p>
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
            <label className="mt-5 flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-900 p-4">
              <input
                checked={toastEnabled}
                className="mt-1 h-4 w-4 accent-cyan-600"
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setToastEnabled(enabled);
                  localStorage.setItem(TOAST_PREFERENCE_KEY, String(enabled));
                  if (!enabled) setNotificationToast(null);
                }}
                type="checkbox"
              />
              <span>
                <span className="block font-semibold">In-app message pop-ups</span>
                <span className="mt-1 block text-sm text-slate-400">Show a toast when a patient sends a new message. Unread counts and the Notifications page remain available when this is off.</span>
              </span>
            </label>
            {staff.role === 'admin' && (
              <div className="mt-8 border-t border-slate-700 pt-6">
                <h2 className="text-xl font-semibold">Coordinator access requests</h2>
                <p className="mt-1 text-sm text-slate-400">Reviewing a request activates the applicant’s account. Pending requests refresh automatically.</p>
                <ul className="mt-4 divide-y divide-slate-700 rounded-xl border border-slate-700">
                  {accessRequests.map((request) => (
                    <li className="p-4" key={request.id}>
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <p className="font-semibold">{request.full_name}</p>
                          <p className="mt-1 text-sm text-slate-400">{request.email}</p>
                          <p className="mt-1 text-xs text-slate-500">Requested {new Date(request.created_at).toLocaleString()}</p>
                          <p className={`mt-2 text-xs ${request.notification_status === 'sent' ? 'text-green-300' : 'text-amber-300'}`}>
                            Admin email: {request.notification_status === 'sent'
                              ? 'Sent'
                              : request.notification_status === 'failed'
                                ? `Failed${request.notification_error ? ` — ${request.notification_error}` : ''}`
                                : request.notification_status === 'not_configured'
                                  ? 'SMTP or admin email is not configured'
                                  : 'Pending'}
                          </p>
                        </div>
                        <div className="flex shrink-0 gap-2">
                          {request.notification_status !== 'sent' && (
                            <button className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold hover:bg-slate-800" onClick={() => void retryAccessRequestEmail(request)} type="button">
                              Retry email
                            </button>
                          )}
                          <button className="rounded-lg bg-green-800 px-3 py-2 text-sm font-semibold text-white hover:bg-green-700" onClick={() => void decideAccessRequest(request, 'approve')} type="button">
                            Approve
                          </button>
                          <button className="rounded-lg border border-red-800 px-3 py-2 text-sm font-semibold text-red-200 hover:bg-red-950" onClick={() => void decideAccessRequest(request, 'reject')} type="button">
                            Reject
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                  {accessRequests.length === 0 && <li className="p-4 text-sm text-slate-400">No pending coordinator access requests.</li>}
                </ul>
              </div>
            )}
            {staff.role === 'admin' && (
              <div className="mt-8 border-t border-slate-700 pt-6">
                <h2 className="text-xl font-semibold">Staff accounts</h2>
                <p className="mt-1 text-sm text-slate-400">Create coordinator accounts and disable access when needed. New staff passwords must be at least 12 characters.</p>
                <form className="mt-4 grid gap-3 rounded-xl border border-slate-700 bg-slate-900 p-4 sm:grid-cols-2" onSubmit={createCoordinator}>
                  <label className="grid gap-1 text-sm text-slate-300">
                    Full name
                    <input className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" maxLength={255} onChange={(event) => setNewStaffName(event.target.value)} required value={newStaffName} />
                  </label>
                  <label className="grid gap-1 text-sm text-slate-300">
                    Email
                    <input className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" maxLength={255} onChange={(event) => setNewStaffEmail(event.target.value)} required type="email" value={newStaffEmail} />
                  </label>
                  <label className="grid gap-1 text-sm text-slate-300">
                    Role
                    <select className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" onChange={(event) => setNewStaffRole(event.target.value === 'admin' ? 'admin' : 'coordinator')} value={newStaffRole}>
                      <option value="coordinator">Coordinator</option>
                      <option value="admin">Admin</option>
                    </select>
                  </label>
                  <label className="grid gap-1 text-sm text-slate-300 sm:col-span-2">
                    Temporary password
                    <input autoComplete="new-password" className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white" minLength={12} onChange={(event) => setNewStaffPassword(event.target.value)} required type="password" value={newStaffPassword} />
                  </label>
                  <button className="justify-self-start rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white" type="submit">Create coordinator</button>
                </form>
                <ul className="mt-4 divide-y divide-slate-700 rounded-xl border border-slate-700">
                  {team.map((account) => (
                    <li className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between" key={account.id}>
                      <div>
                        <p className="font-semibold">{account.full_name} <span className="ml-1 text-xs uppercase text-cyan-300">{account.role}</span></p>
                        <p className="mt-1 text-sm text-slate-400">{account.email} · {account.is_active ? 'Active' : 'Disabled'}</p>
                        <p className="mt-1 text-xs text-slate-500">Last sign-in: {account.last_login_at ? new Date(account.last_login_at).toLocaleString() : 'Never'}</p>
                      </div>
                      {account.role !== 'admin' && (
                        <button className="self-start rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold hover:bg-slate-800" onClick={() => void toggleCoordinator(account)} type="button">
                          {account.is_active ? 'Disable access' : 'Enable access'}
                        </button>
                      )}
                    </li>
                  ))}
                  {team.length === 0 && <li className="p-4 text-sm text-slate-400">No staff accounts loaded.</li>}
                </ul>
              </div>
            )}
          </section>
        )}
        {section === 'activity' && staff.role === 'admin' && (
          <section className="mt-5" aria-label="Staff activity audit">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h1 className="text-3xl font-bold">Staff activity</h1>
                <p className="mt-1 text-sm text-slate-400">Recent sign-ins, failed sign-in attempts, sign-outs, and patient messages read by each staff account.</p>
              </div>
              <button className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold hover:bg-slate-700" onClick={() => void loadAdminData()} type="button">Refresh</button>
            </div>
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-950 p-3 text-sm text-red-200">{error}</p>}
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-700">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-slate-900 text-slate-300">
                  <tr><th className="px-4 py-3">When</th><th className="px-4 py-3">Staff</th><th className="px-4 py-3">Activity</th><th className="px-4 py-3">Message / patient</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {activity.map((event) => (
                    <tr key={event.id}>
                      <td className="px-4 py-3 text-slate-300">{new Date(event.created_at).toLocaleString()}</td>
                      <td className="px-4 py-3">{event.full_name ?? 'Unknown account'}<span className="block text-xs text-slate-400">{event.email ?? ''}</span></td>
                      <td className="px-4 py-3">{event.event_type === 'message_read' ? 'Read patient message' : event.event_type.replace('_', ' ')}</td>
                      <td className="px-4 py-3 text-xs text-slate-400">{event.message_id ?? '—'}{event.patient_id ? <span className="block">Patient: {event.patient_id}</span> : ''}</td>
                    </tr>
                  ))}
                  {activity.length === 0 && <tr><td className="px-4 py-4 text-slate-400" colSpan={4}>No staff activity recorded yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {section === 'about' && (
          <section className="mt-5" aria-label="About Clinical Connect AI">
            <h1 className="text-3xl font-bold">About</h1>
            <p className="mt-3 text-slate-300">Clinical Connect AI is a synthetic-data demonstration workbench for managing patient records, messages, and appointments.</p>
            <p className="mt-3 rounded-lg bg-amber-950 p-4 text-sm text-amber-100">Demonstration only. Do not use real patient information. Coordinator access is not production-secured.</p>
          </section>
        )}
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
                <p className="mt-1 text-sm text-slate-400">Times use your browser’s local timezone. The patient receives a confirmation email and, when scheduled at least 24 hours ahead, a reminder email one day before. In-portal reminders are also created 48 and 24 hours before.</p>
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
                  <ul className="mt-2 space-y-1 text-xs text-slate-400">
                    {appointment.email_deliveries.map((delivery) => (
                      <li key={delivery.id}>
                        {delivery.email_type === 'confirmation' ? 'Confirmation' : '24-hour reminder'} email: {' '}
                        {delivery.status === 'sent' && delivery.sent_at
                          ? `Sent ${new Date(delivery.sent_at).toLocaleString()}`
                          : delivery.status === 'pending' && !delivery.smtp_configured
                            ? 'Queued — SMTP needs to be configured'
                            : delivery.status === 'pending'
                              ? `Queued${delivery.attempts ? ` (attempt ${delivery.attempts}; retry scheduled)` : ''}`
                              : delivery.status === 'sending'
                                ? 'Sending'
                                : delivery.status === 'failed'
                                  ? `Failed after ${delivery.attempts} attempts${delivery.last_error ? `: ${delivery.last_error}` : ''}`
                                  : 'Queued'}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
              {appointments.length === 0 && <li className="py-3 text-sm text-slate-400">No upcoming appointments.</li>}
            </ul>
            </section>
          </div>
        )}
        <p className="mt-5 text-xs text-slate-400">Synthetic demonstration records only. Do not use real patient data.</p>
          </div>
        </div>
      </div>
    </main>
  );
}
