import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const WORKSPACE_PAGES = new Set(["chat", "tasks", "agent", "security"]);

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let message = `Permintaan gagal (${response.status})`;
    if (contentType.includes("application/json")) {
      const body = await response.json();
      const validationDetails = Array.isArray(body?.error?.details)
        ? body.error.details
            .map((detail) => {
              const field = Array.isArray(detail?.loc)
                ? detail.loc.filter((part) => part !== "body").join(".")
                : "";
              return [field, detail?.msg].filter(Boolean).join(": ");
            })
            .filter(Boolean)
        : [];
      message = validationDetails.length
        ? `${body?.error?.message || "Input tidak valid"}: ${validationDetails.join("; ")}`
        : body?.error?.message || body?.detail || message;
    } else {
      const body = await response.text();
      if (body) message = body;
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function localDateTimeValue(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

function formatDue(value) {
  if (!value) return "Tanpa pengingat";
  return new Intl.DateTimeFormat("id-ID", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function parseWebsiteTarget(value) {
  const input = value.trim();
  const scheme = input.match(/^([a-z][a-z\d+.-]*):\/\//i)?.[1]?.toLowerCase();
  if (scheme && scheme !== "https") {
    throw new Error("Gunakan URL HTTPS publik");
  }
  let url;
  try {
    url = new URL(scheme ? input : `https://${input}`);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Masukkan URL website yang valid.");
    }
    throw error;
  }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password) {
    throw new Error("Masukkan URL HTTPS publik tanpa username atau password.");
  }
  if (url.port) {
    throw new Error("Pemeriksaan hanya mendukung port HTTPS standar.");
  }
  if (url.search || url.hash) {
    throw new Error("Query string dan fragment tidak diperiksa; hapus bagian setelah ? atau #.");
  }
  return { targetHost: url.hostname, targetPath: url.pathname || "/" };
}

function isOverdue(todo) {
  return todo.status === "pending" && todo.due_at && new Date(todo.due_at) < new Date();
}

function pageFromHash() {
  const page = window.location.hash.slice(1);
  return WORKSPACE_PAGES.has(page) ? page : "chat";
}

const initialForm = {
  title: "",
  notes: "",
  due_at: "",
  reminder_at: "",
  project_id: "",
  priority: "normal",
};
const emptyDraft = {
  status: "ready",
  title: "",
  notes: "",
  due_at: "",
  reminder_at: "",
  clarification_questions: [],
};
const initialChatMessages = [];

export default function App() {
  const [todos, setTodos] = useState([]);
  const [projects, setProjects] = useState([]);
  const [newProjectName, setNewProjectName] = useState("");
  const [projectSaving, setProjectSaving] = useState(false);
  const [taskSearch, setTaskSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [dueFilter, setDueFilter] = useState("all");
  const [activePage, setActivePage] = useState(pageFromHash);
  const [providerStatus, setProviderStatus] = useState(null);
  const [chatMessages, setChatMessages] = useState(initialChatMessages);
  const [chatConversations, setChatConversations] = useState([]);
  const [chatActions, setChatActions] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [chatActionId, setChatActionId] = useState(null);
  const [chatHistoryLoading, setChatHistoryLoading] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatActionLoading, setChatActionLoading] = useState(false);
  const [chatToolLoading, setChatToolLoading] = useState(false);
  const [chatToolStatus, setChatToolStatus] = useState("");
  const [chatTodoProposal, setChatTodoProposal] = useState(null);
  const [chatToolProposal, setChatToolProposal] = useState(null);
  const [chatProvider, setChatProvider] = useState("");
  const [instruction, setInstruction] = useState("");
  const [aiDraft, setAiDraft] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [agentFiles, setAgentFiles] = useState([]);
  const [agentFilePath, setAgentFilePath] = useState("");
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentConsent, setAgentConsent] = useState(false);
  const [agentProposal, setAgentProposal] = useState(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [commandRunning, setCommandRunning] = useState(false);
  const [commandResult, setCommandResult] = useState(null);
  const [securityScan, setSecurityScan] = useState(null);
  const [securityScanLoading, setSecurityScanLoading] = useState(false);
  const [websiteSecurityUrl, setWebsiteSecurityUrl] = useState("");
  const [websiteSecurityAuthorized, setWebsiteSecurityAuthorized] = useState(false);
  const [websiteSecurityCheck, setWebsiteSecurityCheck] = useState(null);
  const [websiteSecurityLoading, setWebsiteSecurityLoading] = useState(false);
  const [dependencyAudit, setDependencyAudit] = useState(null);
  const [dependencyAuditLoading, setDependencyAuditLoading] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [editingId, setEditingId] = useState(null);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [permission, setPermission] = useState(
    "Notification" in window ? Notification.permission : "unsupported",
  );
  const notifiedIds = useRef(new Set());
  const notificationsLoaded = useRef(false);
  const chatEndRef = useRef(null);

  async function refreshTodos(showLoading = false) {
    if (showLoading) setLoading(true);
    try {
      setTodos(await request("/api/todos"));
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function refreshProjects() {
    try {
      setProjects(await request("/api/projects"));
    } catch (err) {
      setError(err.message);
    }
  }

  async function createProject(event) {
    event.preventDefault();
    setProjectSaving(true);
    setError("");
    try {
      const project = await request("/api/projects", {
        method: "POST",
        body: JSON.stringify({ name: newProjectName }),
      });
      setNewProjectName("");
      setNotice(`Project "${project.name}" dibuat.`);
      await refreshProjects();
    } catch (err) {
      setError(err.message);
    } finally {
      setProjectSaving(false);
    }
  }

  async function renameProject(project) {
    const name = window.prompt("Nama project baru:", project.name);
    if (name === null || name.trim() === project.name) return;
    try {
      await request(`/api/projects/${project.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      await refreshProjects();
      setNotice("Nama project diperbarui.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteProject(project) {
    if (!window.confirm(`Hapus project "${project.name}"? Tugasnya tetap ada tanpa project.`)) return;
    try {
      await request(`/api/projects/${project.id}`, { method: "DELETE" });
      if (form.project_id === String(project.id)) {
        setForm((current) => ({ ...current, project_id: "" }));
      }
      if (projectFilter === String(project.id)) setProjectFilter("all");
      await Promise.all([refreshProjects(), refreshTodos()]);
      setNotice("Project dihapus; tugasnya tetap tersimpan.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshNotifications() {
    try {
      const data = await request("/api/notifications");
      if (
        notificationsLoaded.current &&
        "Notification" in window &&
        Notification.permission === "granted"
      ) {
        data.items
          .filter((item) => !notifiedIds.current.has(item.id))
          .forEach((item) => {
            new Notification("Pengingat tugas", {
              body: item.todo_title,
              tag: `notification-${item.id}`,
            });
            notifiedIds.current.add(item.id);
          });
      } else {
        data.items.forEach((item) => notifiedIds.current.add(item.id));
      }
      notificationsLoaded.current = true;
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshAgentWorkspace() {
    try {
      const [fileData, proposalData] = await Promise.all([
        request("/api/agent/files"),
        request("/api/agent/proposals"),
      ]);
      setAgentFiles(fileData.files);
      setAgentProposal(proposalData.proposals[0] || null);
      if (!agentFilePath && fileData.files.length) setAgentFilePath(fileData.files[0].path);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshChatConversations() {
    try {
      setChatConversations(await request("/api/assistant/conversations"));
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshActiveChatActions(conversationId = activeChatId) {
    if (!conversationId) return;
    try {
      const conversation = await request(`/api/assistant/conversations/${conversationId}`);
      setChatActions(conversation.actions);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createChatConversation(firstMessage) {
    const conversation = await request("/api/assistant/conversations", {
      method: "POST",
      body: JSON.stringify({ first_message: firstMessage }),
    });
    setActiveChatId(conversation.id);
    setChatMessages(conversation.messages);
    await refreshChatConversations();
    return conversation.id;
  }

  async function ensureChatConversation(userMessage) {
    if (!activeChatId) return createChatConversation(userMessage);
    await request(`/api/assistant/conversations/${activeChatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ role: "user", content: userMessage }),
    });
    return activeChatId;
  }

  async function persistAssistantMessage(content, attachments = {}, conversationId = activeChatId) {
    if (!conversationId) return;
    try {
      await request(`/api/assistant/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({ role: "assistant", content, ...attachments }),
      });
      await refreshChatConversations();
    } catch (err) {
      setError(`Hasil tool berjalan, tetapi riwayat gagal disimpan: ${err.message}`);
    }
  }

  async function recordAgentAction(conversationId, actionType, summary, query) {
    const action = await request(`/api/assistant/conversations/${conversationId}/actions`, {
      method: "POST",
      body: JSON.stringify({
        action_type: actionType,
        summary,
        ...(query ? { query } : {}),
      }),
    });
    setChatActions((actions) => [...actions, action]);
    await refreshChatConversations();
    return action.id;
  }

  async function openChatConversation(conversationId) {
    if (chatLoading || chatActionLoading || chatToolLoading || chatHistoryLoading) return;
    setChatHistoryLoading(true);
    setError("");
    try {
      const conversation = await request(`/api/assistant/conversations/${conversationId}`);
      setActiveChatId(conversation.id);
      setChatMessages(conversation.messages.map((message) => ({
        ...message,
        securityScan: message.security_scan,
        webResearch: message.web_research,
      })));
      setChatActions(conversation.actions);
      const pendingAction = conversation.actions.find((action) => action.status === "pending");
      setChatActionId(pendingAction?.id || null);
      setChatToolProposal(pendingAction?.details?.tool_proposal || null);
      setChatTodoProposal(pendingAction?.details?.todo_proposal || null);
      setChatProvider("");
      setChatInput("");
      navigateWorkspace("chat");
    } catch (err) {
      setError(err.message);
    } finally {
      setChatHistoryLoading(false);
    }
  }

  async function deleteChatConversation(conversationId) {
    if (!window.confirm("Hapus percakapan dan catatan aktivitas agent ini?")) return;
    try {
      await request(`/api/assistant/conversations/${conversationId}`, { method: "DELETE" });
      if (activeChatId === conversationId) resetChat();
      await refreshChatConversations();
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateChatAction(status, summary) {
    if (!activeChatId || !chatActionId) return;
    await updateAgentAction(activeChatId, chatActionId, status, summary);
  }

  async function updateAgentAction(conversationId, actionId, status, summary) {
    const updatedAction = await request(`/api/assistant/conversations/${conversationId}/actions/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify({ status, summary }),
    });
    setChatActions((actions) => actions.map((action) => (
      action.id === updatedAction.id ? updatedAction : action
    )));
    await refreshChatConversations();
  }

  useEffect(() => {
    refreshTodos(true);
    refreshProjects();
    refreshNotifications();
    refreshAgentWorkspace();
    refreshChatConversations();
    request("/api/assistant/providers")
      .then(setProviderStatus)
      .catch((err) => setError(err.message));
    const timer = window.setInterval(() => {
      refreshTodos();
      refreshNotifications();
    }, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const syncPage = () => setActivePage(pageFromHash());
    if (!window.location.hash) window.location.hash = "chat";
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chatMessages, chatLoading]);

  const counts = useMemo(() => {
    const pending = todos.filter((todo) => todo.status === "pending");
    return {
      pending: pending.length,
      overdue: pending.filter(isOverdue).length,
      completed: todos.length - pending.length,
    };
  }, [todos]);

  const visibleTodos = useMemo(() => {
    const query = taskSearch.trim().toLocaleLowerCase();
    return todos.filter((todo) => {
      if (filter === "pending" && todo.status !== "pending") return false;
      if (filter === "completed" && todo.status !== "completed") return false;
      if (projectFilter === "none" && todo.project_id !== null) return false;
      if (projectFilter !== "all" && projectFilter !== "none" && String(todo.project_id) !== projectFilter) return false;
      if (priorityFilter !== "all" && todo.priority !== priorityFilter) return false;
      if (dueFilter === "overdue" && !isOverdue(todo)) return false;
      if (dueFilter === "scheduled" && !todo.due_at) return false;
      if (dueFilter === "unscheduled" && todo.due_at) return false;
      if (query && !`${todo.title} ${todo.notes || ""}`.toLocaleLowerCase().includes(query)) return false;
      return true;
    });
  }, [dueFilter, filter, priorityFilter, projectFilter, taskSearch, todos]);
  const providerNameById = Object.fromEntries(
    (providerStatus?.providers || []).map((provider) => [provider.id, provider.name]),
  );
  const activeProviderOrder = providerStatus
    ? [providerStatus.default_provider, ...providerStatus.fallback_order]
        .filter((providerId) => providerStatus.providers.some(
          (provider) => provider.id === providerId && provider.configured,
        ))
        .map((providerId) => providerNameById[providerId])
    : [];

  function updateForm(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  function resetForm() {
    setForm(initialForm);
    setEditingId(null);
  }

  async function saveTodo(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        title: form.title,
        notes: form.notes || null,
        project_id: form.project_id ? Number(form.project_id) : null,
        priority: form.priority,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        reminder_at: form.reminder_at ? new Date(form.reminder_at).toISOString() : null,
      };
      if (editingId) {
        await request(`/api/todos/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        setNotice("Perubahan tugas disimpan.");
      } else {
        await request("/api/todos", { method: "POST", body: JSON.stringify(payload) });
        setNotice("Tugas berhasil ditambahkan.");
      }
      resetForm();
      await refreshTodos();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function generateDraft(event) {
    event.preventDefault();
    setAiLoading(true);
    setError("");
    setAiDraft(null);
    try {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Jakarta";
      const response = await request("/api/assistant/drafts", {
        method: "POST",
        body: JSON.stringify({ instruction, timezone }),
      });
      setAiDraft({ ...emptyDraft, ...response.draft, provider: response.provider, model: response.model });
    } catch (err) {
      setError(err.message);
    } finally {
      setAiLoading(false);
    }
  }

  async function sendChatMessage(event) {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading || chatToolLoading || chatTodoProposal?.status === "ready" || chatToolProposal) return;
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Jakarta";
    const messages = [...chatMessages, { role: "user", content: text }].slice(-16);
    setChatMessages(messages);
    setChatInput("");
    setChatLoading(true);
    setError("");
    try {
      const response = await request("/api/assistant/chat", {
        method: "POST",
        body: JSON.stringify({
          messages,
          timezone,
          ...(activeChatId ? { conversation_id: activeChatId } : {}),
        }),
      });
      setActiveChatId(response.conversation_id);
      setChatMessages([
        ...messages,
        {
          role: "assistant",
          content: response.reply,
          todo_proposal: response.todo_proposal,
          tool_proposal: response.tool_proposal,
          action_id: response.action_id,
        },
      ].slice(-16));
      setChatTodoProposal(response.todo_proposal);
      setChatToolProposal(response.tool_proposal);
      setChatActionId(response.action_id);
      setChatProvider(`${providerNameById[response.provider] || response.provider} · ${response.model}`);
      await refreshChatConversations();
      await refreshActiveChatActions(response.conversation_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setChatLoading(false);
    }
  }

  async function confirmChatTodo() {
    if (!chatTodoProposal || chatTodoProposal.status !== "ready") return;
    if (!window.confirm(`Simpan draft "${chatTodoProposal.title}" sebagai tugas?`)) return;
    setChatActionLoading(true);
    setError("");
    let actionApproved = false;
    try {
      if (chatActionId) {
        await updateChatAction("approved", chatTodoProposal.title);
        actionApproved = true;
      }
      await request("/api/todos", {
        method: "POST",
        body: JSON.stringify({
          title: chatTodoProposal.title,
          notes: chatTodoProposal.notes || null,
          due_at: chatTodoProposal.due_at
            ? new Date(chatTodoProposal.due_at).toISOString()
            : null,
          reminder_at: chatTodoProposal.reminder_at
            ? new Date(chatTodoProposal.reminder_at).toISOString()
            : null,
        }),
      });
      if (chatActionId) await updateChatAction("completed", `Tugas disimpan: ${chatTodoProposal.title}`);
      setChatTodoProposal(null);
      setChatActionId(null);
      await refreshActiveChatActions();
      const completionMessage = "Tugas berhasil disimpan setelah konfirmasi kamu.";
      setChatMessages((messages) => [
        ...messages,
        { role: "assistant", content: completionMessage },
      ].slice(-16));
      await persistAssistantMessage(completionMessage);
      setNotice("Draft chat dikonfirmasi dan disimpan sebagai tugas.");
      await refreshTodos();
    } catch (err) {
      if (chatActionId && actionApproved) {
        try {
          await updateChatAction("failed", `Penyimpanan tugas gagal: ${err.message}`);
        } catch (actionError) {
          setError(`${err.message}; status aktivitas juga gagal disimpan: ${actionError.message}`);
        }
      }
      setError(err.message);
    } finally {
      setChatActionLoading(false);
    }
  }

  async function rejectChatAction() {
    if (chatActionLoading || chatToolLoading) return;
    setChatActionLoading(true);
    setError("");
    try {
      if (chatActionId) await updateChatAction("rejected", "Usulan ditolak pengguna.");
      setChatTodoProposal(null);
      setChatToolProposal(null);
      setChatActionId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setChatActionLoading(false);
    }
  }

  function resetChat() {
    if (chatLoading || chatActionLoading || chatToolLoading) return;
    setChatMessages(initialChatMessages);
    setActiveChatId(null);
    setChatActions([]);
    setChatActionId(null);
    setChatInput("");
    setChatTodoProposal(null);
    setChatToolProposal(null);
    setChatProvider("");
  }

  function startNewChat() {
    resetChat();
    navigateWorkspace("chat");
    setError("");
    setNotice("");
  }

  function navigateWorkspace(page) {
    if (!WORKSPACE_PAGES.has(page)) return;
    if (window.location.hash !== `#${page}`) window.location.hash = page;
    setActivePage(page);
  }

  function updateAiDraft(event) {
    const { name, value } = event.target;
    setAiDraft({ ...aiDraft, [name]: value });
  }

  async function confirmAiDraft() {
    if (!aiDraft?.title || aiDraft.status !== "ready") return;
    setSaving(true);
    setError("");
    try {
      await request("/api/todos", {
        method: "POST",
        body: JSON.stringify({
          title: aiDraft.title,
          notes: aiDraft.notes || null,
          due_at: aiDraft.due_at ? new Date(aiDraft.due_at).toISOString() : null,
          reminder_at: aiDraft.reminder_at ? new Date(aiDraft.reminder_at).toISOString() : null,
        }),
      });
      setNotice("Draft AI dikonfirmasi dan disimpan sebagai tugas.");
      setAiDraft(null);
      setInstruction("");
      await refreshTodos();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function createCodeProposal(event) {
    event.preventDefault();
    setAgentLoading(true);
    setError("");
    setCommandResult(null);
    try {
      const proposal = await request("/api/agent/proposals", {
        method: "POST",
        body: JSON.stringify({
          instruction: agentInstruction,
          file_path: agentFilePath,
          consent_to_send_source: agentConsent,
        }),
      });
      setAgentProposal(proposal);
      setNotice("Patch dibuat sebagai proposal. File belum berubah.");
      setAgentConsent(false);
      await refreshAgentWorkspace();
    } catch (err) {
      setError(err.message);
    } finally {
      setAgentLoading(false);
    }
  }

  async function reviewCodeProposal(action) {
    if (!agentProposal) return;
    if (action === "approve" && !window.confirm(
      `Terapkan patch ke ${agentProposal.file_path}? Perubahan ini akan menulis file di workspace.`,
    )) return;
    if (action === "reject" && !window.confirm("Tolak proposal ini? File tidak akan diubah.")) return;
    setAgentLoading(true);
    setError("");
    try {
      const proposal = await request(
        `/api/agent/proposals/${agentProposal.id}/${action}`,
        { method: "POST" },
      );
      setAgentProposal(proposal);
      setNotice(action === "approve" ? "Patch diterapkan ke file." : "Proposal ditolak; file tidak diubah.");
      await refreshAgentWorkspace();
    } catch (err) {
      setError(err.message);
    } finally {
      setAgentLoading(false);
    }
  }

  async function runBackendTests() {
    if (!window.confirm(
      "Jalankan command tetap `python -m pytest -q` di project ini? Test code akan dieksekusi. Periksa patch dan test terlebih dahulu.",
    )) return;
    setCommandRunning(true);
    setError("");
    setCommandResult(null);
    try {
      const result = await request("/api/agent/commands/run", {
        method: "POST",
        body: JSON.stringify({ command_id: "backend_tests", confirm_execution: true }),
      });
      setCommandResult(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setCommandRunning(false);
    }
  }

  async function runSecurityScan() {
    setSecurityScanLoading(true);
    setError("");
    setNotice("");
    try {
      const result = await request("/api/agent/security-scan", { method: "POST" });
      setSecurityScan(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSecurityScanLoading(false);
    }
  }

  async function runWebsiteSecurityCheck(event) {
    event.preventDefault();
    if (!websiteSecurityUrl.trim() || !websiteSecurityAuthorized || websiteSecurityLoading) return;
    let target;
    try {
      target = parseWebsiteTarget(websiteSecurityUrl);
    } catch (err) {
      setError(err.message);
      return;
    }
    const displayUrl = `https://${target.targetHost}${target.targetPath}`;
    if (!window.confirm(
      `Konfirmasi: kamu memiliki atau mendapat izin untuk memeriksa ${displayUrl}. Pemeriksaan hanya satu HTTPS GET, tanpa query/fragment dan tanpa mengikuti redirect. Pastikan path ini read-only karena GET pada website dapat memiliki efek samping.`,
    )) return;
    setWebsiteSecurityLoading(true);
    setWebsiteSecurityCheck(null);
    setError("");
    try {
      const result = await request("/api/agent/website-security-check", {
        method: "POST",
        body: JSON.stringify({
          target_host: target.targetHost,
          target_path: target.targetPath,
          confirm_authorized: true,
        }),
      });
      setWebsiteSecurityCheck(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setWebsiteSecurityLoading(false);
    }
  }

  async function runDependencyAudit() {
    if (dependencyAuditLoading || !window.confirm(
      "Jalankan npm audit dan pip-audit? Nama serta versi dependency akan dikirim ke layanan advisory npm/PyPI. Source code dan secrets tidak dikirim; tidak ada paket yang diubah.",
    )) return;
    setDependencyAuditLoading(true);
    setDependencyAudit(null);
    setError("");
    try {
      const result = await request("/api/agent/dependency-audit", {
        method: "POST",
        body: JSON.stringify({ confirm_external_lookup: true }),
      });
      setDependencyAudit(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setDependencyAuditLoading(false);
    }
  }

  async function runChatSecurityScan(recordUserMessage = true, approvedActionId = null) {
    if (chatToolLoading || chatLoading || chatActionLoading) return;
    const userMessage = "Jalankan analisis keamanan lokal pada project.";
    let conversationId = activeChatId;
    let actionId = approvedActionId;
    if (recordUserMessage) {
      try {
        const isNewConversation = !conversationId;
        conversationId = await ensureChatConversation(userMessage);
        actionId = await recordAgentAction(
          conversationId,
          "local_security_scan",
          "Scan keamanan read-only pada project lokal.",
        );
        if (!isNewConversation) {
          setChatMessages((messages) => [
            ...messages,
            { role: "user", content: userMessage },
          ].slice(-16));
        }
      } catch (err) {
        setError(err.message);
        return false;
      }
    }
    if (actionId) setChatActionId(actionId);
    setChatToolLoading(true);
    setChatToolStatus("Memeriksa source project secara lokal…");
    setError("");
    let result;
    try {
      result = await request("/api/agent/security-scan", { method: "POST" });
    } catch (err) {
      const failureMessage = `Analisis lokal gagal: ${err.message}`;
      setChatMessages((messages) => [...messages, { role: "assistant", content: failureMessage }].slice(-16));
      await persistAssistantMessage(failureMessage, {}, conversationId);
      if (actionId) {
        try {
          await updateAgentAction(conversationId, actionId, "failed", failureMessage);
        } catch (actionError) {
          setError(`${failureMessage}; status aktivitas gagal disimpan: ${actionError.message}`);
        }
        setChatActionId(null);
      }
      return false;
    } finally {
      setChatToolLoading(false);
      setChatToolStatus("");
    }
    setSecurityScan(result);
    const summary = result.findings.length
      ? `Analisis lokal selesai: ${result.scanned_files} file diperiksa. Ada ${result.high_count} temuan prioritas tinggi, ${result.medium_count} perlu review, dan ${result.low_count} rendah.`
      : `Analisis lokal selesai: ${result.scanned_files} file diperiksa dan tidak ada pola berisiko yang terdeteksi. Hasil bersih bukan jaminan keamanan.`;
    setChatMessages((messages) => [
      ...messages,
      { role: "assistant", content: summary, securityScan: result },
    ].slice(-16));
    await persistAssistantMessage(summary, { security_scan: result }, conversationId);
    if (actionId) {
      try {
        await updateAgentAction(conversationId, actionId, "completed", summary);
      } catch (err) {
        setError(`Scan selesai, tetapi status aktivitas gagal disimpan: ${err.message}`);
      }
      setChatActionId(null);
    }
    return true;
  }

  async function runChatWebResearch(queryText = chatInput, recordUserMessage = true, approvedActionId = null) {
    const query = queryText.trim();
    if (query.length < 3 || chatToolLoading || chatLoading || chatActionLoading) return;
    let conversationId = activeChatId;
    let actionId = approvedActionId;
    if (recordUserMessage) {
      try {
        const isNewConversation = !conversationId;
        conversationId = await ensureChatConversation(query);
        actionId = await recordAgentAction(
          conversationId,
          "public_web_research",
          "Riset web publik yang diminta pengguna.",
          query,
        );
        if (!isNewConversation) {
          setChatMessages((messages) => [
            ...messages,
            { role: "user", content: query },
          ].slice(-16));
        }
      } catch (err) {
        setError(err.message);
        return false;
      }
      setChatInput("");
    }
    if (actionId) setChatActionId(actionId);
    setChatToolLoading(true);
    setChatToolStatus("Mencari sumber publik dengan Google Search…");
    setError("");
    let result;
    try {
      result = await request("/api/agent/research", {
        method: "POST",
        body: JSON.stringify({ query }),
      });
    } catch (err) {
      const failureMessage = `Riset web gagal: ${err.message}`;
      setChatMessages((messages) => [...messages, { role: "assistant", content: failureMessage }].slice(-16));
      await persistAssistantMessage(failureMessage, {}, conversationId);
      if (actionId) {
        try {
          await updateAgentAction(conversationId, actionId, "failed", failureMessage);
        } catch (actionError) {
          setError(`${failureMessage}; status aktivitas gagal disimpan: ${actionError.message}`);
        }
        setChatActionId(null);
      }
      return false;
    } finally {
      setChatToolLoading(false);
      setChatToolStatus("");
    }
    setChatMessages((messages) => [
      ...messages,
      { role: "assistant", content: result.answer, webResearch: result },
    ].slice(-16));
    await persistAssistantMessage(result.answer, { web_research: result }, conversationId);
    if (actionId) {
      try {
        await updateAgentAction(conversationId, actionId, "completed", result.answer.slice(0, 1000));
      } catch (err) {
        setError(`Riset selesai, tetapi status aktivitas gagal disimpan: ${err.message}`);
      }
      setChatActionId(null);
    }
    return true;
  }

  async function approveChatToolProposal() {
    const proposal = chatToolProposal;
    if (!proposal || chatToolLoading) return;
    const isResearch = proposal.tool_id === "public_web_research";
    const approved = window.confirm(
      isResearch
        ? `Kirim query ini ke Google/Gemini untuk pencarian web?\n\n${proposal.query}`
        : "Jalankan scan keamanan read-only pada source project lokal? Source tidak dikirim ke AI.",
    );
    if (!approved) return;
    setChatActionLoading(true);
    setError("");
    try {
      await updateChatAction("approved", proposal.reason);
      setChatToolProposal(null);
      setChatActionLoading(false);
      if (isResearch) {
        await runChatWebResearch(proposal.query, false, chatActionId);
      } else {
        await runChatSecurityScan(false, chatActionId);
      }
    } catch (err) {
      setError(err.message);
      setChatActionLoading(false);
    }
  }

  function editTodo(todo) {
    setEditingId(todo.id);
    setForm({
      title: todo.title,
      notes: todo.notes || "",
      due_at: localDateTimeValue(todo.due_at),
      reminder_at: localDateTimeValue(todo.reminder_at),
      project_id: todo.project_id ? String(todo.project_id) : "",
      priority: todo.priority || "normal",
    });
    document.getElementById("task-title")?.focus();
  }

  async function toggleTodo(todo) {
    const nextStatus = todo.status === "completed" ? "pending" : "completed";
    try {
      await request(`/api/todos/${todo.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await refreshTodos();
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteTodo(todo) {
    if (!window.confirm(`Hapus tugas "${todo.title}"?`)) return;
    try {
      await request(`/api/todos/${todo.id}`, { method: "DELETE" });
      setNotice("Tugas dihapus.");
      await refreshTodos();
    } catch (err) {
      setError(err.message);
    }
  }

  async function enableNotifications() {
    if (!("Notification" in window)) {
      setPermission("unsupported");
      return;
    }
    setPermission(await Notification.requestPermission());
  }

  async function markNotificationRead(notification) {
    try {
      await request(`/api/notifications/${notification.id}/read`, { method: "PATCH" });
      await refreshNotifications();
    } catch (err) {
      setError(err.message);
    }
  }

  async function markAllNotificationsRead() {
    try {
      await request("/api/notifications/read-all", { method: "PATCH" });
      await refreshNotifications();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" type="button" onClick={startNewChat} aria-label="Digital Operator beranda">
          <span className="brand-mark">do</span>
          <span>
            <strong>digital operator</strong>
            <small>AI WORKSPACE</small>
          </span>
        </button>
        <button
          className="new-chat-button"
          type="button"
          onClick={startNewChat}
          disabled={chatLoading || chatActionLoading || chatToolLoading || chatHistoryLoading}
        >
          <span>＋</span> Chat baru
        </button>
        <div className="chat-history">
          <div className="sidebar-section-label">RIWAYAT CHAT</div>
          {chatConversations.length ? (
            <div className="chat-history-list">
              {chatConversations.map((conversation) => (
                <div
                  className={`chat-history-item ${activeChatId === conversation.id ? "active" : ""}`}
                  key={conversation.id}
                >
                  <button
                    className="chat-history-open"
                    type="button"
                    onClick={() => openChatConversation(conversation.id)}
                    disabled={chatHistoryLoading || chatLoading || chatActionLoading || chatToolLoading}
                    title={conversation.last_message}
                  >
                    <strong>{conversation.title}</strong>
                    <small>{conversation.message_count} pesan</small>
                  </button>
                  <button
                    className="chat-history-delete"
                    type="button"
                    aria-label={`Hapus percakapan ${conversation.title}`}
                    onClick={() => deleteChatConversation(conversation.id)}
                    disabled={chatHistoryLoading || chatLoading || chatActionLoading || chatToolLoading}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="chat-history-empty">
              {chatHistoryLoading ? "Memuat riwayat..." : "Belum ada percakapan tersimpan."}
            </p>
          )}
        </div>
        <div className="sidebar-section-label">AGENT</div>
        <nav className="workspace-nav" aria-label="Navigasi workspace">
          <button
            className={`nav-item ${activePage === "chat" ? "active" : ""}`}
            onClick={() => navigateWorkspace("chat")}
            type="button"
          >
            <span className="nav-icon">✳</span> Agent
          </button>
        </nav>
        <div className="sidebar-section-label tools-label">TOOLS</div>
        <nav className="workspace-nav" aria-label="Tools workspace">
          <button
            className={`nav-item ${activePage === "tasks" ? "active" : ""}`}
            onClick={() => navigateWorkspace("tasks")}
            type="button"
          >
            <span className="nav-icon">▦</span> Tugas & pengingat
            <span className="nav-count">{counts.pending}</span>
          </button>
          <button
            className={`nav-item ${activePage === "agent" ? "active" : ""}`}
            onClick={() => navigateWorkspace("agent")}
            type="button"
          >
            <span className="nav-icon">⌘</span> Coding agent
            {agentProposal?.status === "pending" && <span className="nav-indicator" />}
          </button>
          <button
            className={`nav-item ${activePage === "security" ? "active" : ""}`}
            onClick={() => navigateWorkspace("security")}
            type="button"
          >
            <span className="nav-icon">⬡</span> Security lokal
          </button>
        </nav>
        <div className="sidebar-section-label tools-label">MODEL</div>
        <div className="sidebar-provider">
          <span className={`provider-status-dot ${activeProviderOrder.length ? "ready" : ""}`} />
          <div>
            <strong>{activeProviderOrder.length ? "AI siap digunakan" : "Provider belum disiapkan"}</strong>
            <small>{activeProviderOrder.length ? activeProviderOrder[0] : "Atur provider di .env"}</small>
          </div>
        </div>
        <div className="sidebar-bottom">
          <div className="profile-avatar">DO</div>
          <div className="profile-copy">
            <strong>Workspace lokal</strong>
            <span>v0.3.0 · Preview</span>
          </div>
          <span className="status-dot" title="Workspace lokal" />
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>
            {activePage === "chat"
              ? "Agent"
              : activePage === "tasks"
                ? "Tugas"
                : activePage === "security"
                  ? "Security lokal"
                  : "Coding agent"}
          </div>
          <div className="topbar-right">
            <span className="today-label">
              {new Intl.DateTimeFormat("id-ID", {
                weekday: "long",
                day: "numeric",
                month: "long",
              }).format(new Date())}
            </span>
            <div className="notification-menu">
              <button
                className={`notification-button ${unreadCount ? "has-unread" : ""}`}
                onClick={() => setNotificationOpen(!notificationOpen)}
                type="button"
                aria-expanded={notificationOpen}
                aria-label={`Notifikasi, ${unreadCount} belum dibaca`}
              >
                <span aria-hidden="true">♧</span>
                Notifikasi
                {unreadCount > 0 && <b>{unreadCount}</b>}
              </button>
              {notificationOpen && (
                <section className="notification-panel" aria-label="Inbox notifikasi">
                  <div className="notification-panel-heading">
                    <div><strong>Pengingat</strong><small>{unreadCount} belum dibaca</small></div>
                    {unreadCount > 0 && (
                      <button type="button" onClick={markAllNotificationsRead}>Tandai semua dibaca</button>
                    )}
                  </div>
                  {permission !== "granted" && (
                    <button className="browser-notification-prompt" type="button" onClick={enableNotifications}>
                      Aktifkan notifikasi browser
                    </button>
                  )}
                  <div className="notification-list">
                    {notifications.length ? notifications.map((item) => (
                      <button
                        key={item.id}
                        className={`notification-item ${item.is_read ? "" : "unread"}`}
                        type="button"
                        onClick={() => !item.is_read && markNotificationRead(item)}
                      >
                        <span className="notification-item-dot" />
                        <span><strong>{item.todo_title}</strong><small>{formatDue(item.delivered_at)}</small></span>
                      </button>
                    )) : (
                      <p className="notification-empty">Belum ada pengingat terkirim.</p>
                    )}
                  </div>
                </section>
              )}
            </div>
          </div>
        </header>

        <div className="content">
          {error && <div className="alert error" role="alert">{error}</div>}
          {notice && <div className="alert success" role="status">{notice}</div>}

          {activePage === "tasks" && (
            <>
          <div className="page-heading">
            <div>
              <div className="eyebrow">PERSONAL TASK MANAGER</div>
              <h1>Urus yang penting.</h1>
              <p>Satu langkah kecil yang tercatat adalah satu hal yang lebih terkendali.</p>
            </div>
            <div className="heading-date">
              <span className="heading-date-icon">✳</span>
              <span><strong>{counts.pending}</strong><small>tugas terbuka</small></span>
            </div>
          </div>

          <div className="summary-grid">
            <article className="summary-card">
              <span className="summary-icon ink">↗</span>
              <div><span>Belum selesai</span><strong>{counts.pending}</strong></div>
              <small>tugas aktif</small>
            </article>
            <article className={`summary-card ${counts.overdue ? "attention" : ""}`}>
              <span className="summary-icon coral">◷</span>
              <div><span>Perlu perhatian</span><strong>{counts.overdue}</strong></div>
              <small>{counts.overdue ? "sudah melewati waktu" : "tidak ada yang terlambat"}</small>
            </article>
            <article className="summary-card">
              <span className="summary-icon green">✓</span>
              <div><span>Selesai</span><strong>{counts.completed}</strong></div>
              <small>tuntas sejauh ini</small>
            </article>
          </div>
            </>
          )}

          {activePage === "chat" && (
            <section className={`assistant-chat-card ${chatMessages.length ? "has-messages" : "is-empty"}`}>
              <div className="assistant-chat-topline">
                <span className="assistant-live-indicator"><i /> {chatProvider || (activeProviderOrder.length ? activeProviderOrder[0] : "AI belum dikonfigurasi")}</span>
                <button className="chat-reset-button" type="button" onClick={resetChat} disabled={chatLoading || chatActionLoading || chatToolLoading}>
                  + Chat baru
                </button>
              </div>
              {chatMessages.length ? (
                <div className="assistant-chat-transcript" aria-live="polite">
                  {chatMessages.map((message, index) => (
                    <div
                      className={`chat-message ${message.role}`}
                      key={`${index}-${message.content.slice(0, 16)}`}
                    >
                      {message.role === "assistant" && <span className="chat-avatar">✳</span>}
                      <div className="chat-message-body">
                        <span>{message.role === "assistant" ? "Digital Operator" : "Kamu"}</span>
                        <p>{message.content}</p>
                        {message.securityScan && (
                          <div className="chat-security-result">
                            <div className="chat-security-metrics">
                              <span><strong>{message.securityScan.scanned_files}</strong> file</span>
                              <span><strong>{message.securityScan.high_count}</strong> tinggi</span>
                              <span><strong>{message.securityScan.medium_count}</strong> review</span>
                            </div>
                            {message.securityScan.findings.length > 0 && (
                              <ul>
                                {message.securityScan.findings.slice(0, 5).map((finding) => (
                                  <li key={`${finding.rule_id}-${finding.file_path}-${finding.line}`}>
                                    <strong>{finding.title}</strong>
                                    <code>{finding.file_path}:{finding.line}</code>
                                  </li>
                                ))}
                                {message.securityScan.findings.length > 5 && (
                                  <li>dan {message.securityScan.findings.length - 5} temuan lainnya</li>
                                )}
                              </ul>
                            )}
                            <button type="button" onClick={() => navigateWorkspace("security")}>
                              Lihat laporan lengkap →
                            </button>
                          </div>
                        )}
                        {message.webResearch && message.webResearch.citations.length > 0 && (
                          <div className="chat-research-sources">
                            <strong>Sumber publik · Google Search</strong>
                            <ul>
                              {message.webResearch.citations.map((citation) => (
                                <li key={citation.url}>
                                  <a href={citation.url} target="_blank" rel="noopener noreferrer">
                                    {citation.title} ↗
                                  </a>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {chatToolLoading && (
                    <div className="chat-message assistant">
                      <span className="chat-avatar">⬡</span>
                      <div className="chat-message-body"><span>Digital Operator · Tool</span><p className="thinking-dots">{chatToolStatus || "Sedang memproses permintaan"}<span>.</span><span>.</span><span>.</span></p></div>
                    </div>
                  )}
                  {chatLoading && (
                    <div className="chat-message assistant">
                      <span className="chat-avatar">✳</span>
                      <div className="chat-message-body"><span>Digital Operator</span><p className="thinking-dots">Sedang berpikir<span>.</span><span>.</span><span>.</span></p></div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
              ) : (
                <div className="chat-welcome">
                  <span className="chat-welcome-mark">✳</span>
                  <div className="eyebrow">DIGITAL OPERATOR AI</div>
                  <h1>Hai, bro. Mau beresin apa hari ini?</h1>
                  <p>Ngobrol, susun rencana, atau mulai dari ide yang masih berantakan.</p>
                  <div className="chat-suggestions">
                    {[
                      ["✧", "Bantu susun rencana", "Bantu aku pecah project ini jadi langkah-langkah kecil."],
                      ["▦", "Buat daftar tugas", "Buatkan tugas untuk review progress project hari ini."],
                      ["⌘", "Bantu coding", "Bantu aku memahami cara mulai memperbaiki bug di project ini."],
                      ["⬡", "Analisis project", ""],
                    ].map(([icon, title, prompt]) => (
                      <button
                        key={title}
                        type="button"
                        onClick={() => title === "Analisis project" ? runChatSecurityScan() : setChatInput(prompt)}
                        disabled={title === "Analisis project" && (chatToolLoading || chatLoading || chatActionLoading || Boolean(chatToolProposal))}
                      >
                        <span>{icon}</span><strong>{title}</strong><i>↗</i>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {chatToolProposal && (
              <div className="chat-tool-proposal">
                <div>
                  <span className="eyebrow">USULAN TOOL · MENUNGGU PERSETUJUAN</span>
                  <h3>{chatToolProposal.tool_id === "public_web_research" ? "Riset web publik" : "Analisis security project lokal"}</h3>
                  <p>{chatToolProposal.reason}</p>
                  {chatToolProposal.tool_id === "public_web_research" && (
                    <small className="chat-tool-query">Query yang akan dikirim: {chatToolProposal.query}</small>
                  )}
                  <small>
                    {chatToolProposal.tool_id === "public_web_research"
                      ? "Query dikirim ke Google/Gemini. File project tidak ikut dikirim."
                      : "Read-only. Tidak ada source yang dikirim ke provider AI."}
                  </small>
                </div>
                <div className="chat-tool-actions">
                  <button
                    className="cancel-button"
                    type="button"
                    onClick={rejectChatAction}
                    disabled={chatToolLoading || chatActionLoading}
                  >
                    Tolak
                  </button>
                  <button
                    className="submit-button"
                    type="button"
                    onClick={approveChatToolProposal}
                    disabled={chatToolLoading}
                  >
                    Setujui & jalankan
                  </button>
                </div>
              </div>
              )}
              {chatActions.length > 0 && (
                <section className="chat-activity-log" aria-label="Riwayat aktivitas agent">
                  <span className="eyebrow">AKTIVITAS AGENT</span>
                  {chatActions.slice().reverse().map((action) => (
                    <div className="chat-activity-row" key={action.id}>
                      <span className={`chat-activity-status ${action.status}`}>{action.status}</span>
                      <div>
                        <strong>{action.summary}</strong>
                        <small>{action.action_type.replaceAll("_", " ")}</small>
                      </div>
                    </div>
                  ))}
                </section>
              )}
              {chatTodoProposal?.status === "ready" && (
              <div className="chat-tool-proposal">
                <div>
                  <span className="eyebrow">USULAN TOOL · BUAT TUGAS</span>
                  <h3>{chatTodoProposal.title}</h3>
                  {chatTodoProposal.notes && <p>{chatTodoProposal.notes}</p>}
                  {chatTodoProposal.due_at && <small>Tenggat: {formatDue(chatTodoProposal.due_at)}</small>}
                  {chatTodoProposal.reminder_at && <small> · Pengingat: {formatDue(chatTodoProposal.reminder_at)}</small>}
                </div>
                <div className="chat-tool-actions">
                  <button
                    className="cancel-button"
                    type="button"
                    onClick={rejectChatAction}
                    disabled={chatActionLoading}
                  >
                    Tolak
                  </button>
                  <button
                    className="submit-button"
                    type="button"
                    onClick={confirmChatTodo}
                    disabled={chatActionLoading}
                  >
                    {chatActionLoading ? "Menyimpan..." : "Setujui & simpan"}
                  </button>
                </div>
              </div>
              )}
              {chatTodoProposal?.status === "needs_clarification" && (
              <div className="chat-clarification">
                <strong>Perlu detail sebelum membuat draft</strong>
                <ul>
                  {chatTodoProposal.clarification_questions.map((question) => (
                    <li key={question}>{question}</li>
                  ))}
                </ul>
              </div>
              )}
              <div className="chat-composer-wrap">
                <form className="assistant-chat-form" onSubmit={sendChatMessage}>
                  <textarea
                    value={chatInput}
                    onChange={(event) => setChatInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        event.currentTarget.form.requestSubmit();
                      }
                    }}
                    placeholder="Kirim pesan ke Digital Operator..."
                    rows={2}
                    maxLength={4000}
                    aria-label="Pesan untuk Digital Operator"
                    required
                  />
                  <button
                    className="chat-send-button"
                    type="submit"
                    disabled={chatLoading || chatToolLoading || chatInput.trim().length === 0 || chatTodoProposal?.status === "ready" || Boolean(chatToolProposal)}
                    aria-label="Kirim pesan"
                  >
                    {chatLoading ? "…" : "↑"}
                  </button>
                </form>
                <div className="assistant-tool-shortcuts" aria-label="Tools agent">
                  <span>Gunakan tool:</span>
                  <button type="button" onClick={() => navigateWorkspace("tasks")}>▦ Tugas</button>
                  <button type="button" onClick={() => navigateWorkspace("agent")}>⌘ Coding</button>
                  <button
                    type="button"
                    onClick={runChatWebResearch}
                    disabled={chatInput.trim().length < 3 || chatToolLoading || chatLoading || chatActionLoading || Boolean(chatToolProposal)}
                    title="Query dikirim ke Google Gemini untuk pencarian web."
                  >
                    ◎ Riset web
                  </button>
                  <button type="button" onClick={runChatSecurityScan} disabled={chatToolLoading || chatLoading || chatActionLoading || Boolean(chatToolProposal)}>⬡ Analisis project</button>
                </div>
                <p className="chat-disclaimer">
                  AI bisa membuat kesalahan. Riset web mengirim query ke Google/Gemini—jangan masukkan rahasia. <span>·</span> Enter untuk chat, Shift + Enter untuk baris baru
                </p>
              </div>
            </section>
          )}

          {activePage === "tasks" && (
          <section className="ai-planner-card">
            <div className="ai-planner-heading">
              <span className="ai-planner-icon">✳</span>
              <div>
                <h2>Rencanakan dengan AI</h2>
                <p>Tulis instruksi biasa. AI menyiapkan draft untuk lo periksa—belum ada tugas yang disimpan.</p>
              </div>
              <span className={`provider-indicator ${providerStatus?.providers?.some((item) => item.configured) ? "ready" : ""}`}>
                <i /> {activeProviderOrder.length
                  ? `Urutan: ${activeProviderOrder.join(" → ")}`
                  : "Provider belum disiapkan"}
              </span>
            </div>
            <form className="ai-instruction-form" onSubmit={generateDraft}>
              <textarea
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Contoh: Ingatkan aku bayar listrik besok jam 9 pagi."
                rows={2}
                maxLength={4000}
                required
                aria-label="Instruksi untuk AI"
              />
              <button className="submit-button" type="submit" disabled={aiLoading || instruction.trim().length < 3}>
                {aiLoading ? "Menyusun draft..." : "Buat draft"}
                {!aiLoading && <span>✳</span>}
              </button>
            </form>
            <p className="ai-privacy-note">Instruksi dikirim ke provider yang dicoba (termasuk fallback). Jangan masukkan data rahasia.</p>

            {aiDraft && (
              <div className="ai-draft">
                <div className="ai-draft-title">
                  <div>
                    <span className="eyebrow">DRAFT UNTUK DITINJAU</span>
                    <h3>{aiDraft.status === "ready" ? "Periksa sebelum disimpan" : "Butuh klarifikasi"}</h3>
                  </div>
                  <span className="ai-model-label">{aiDraft.provider} · {aiDraft.model}</span>
                </div>
                {aiDraft.status === "needs_clarification" ? (
                  <div className="clarification-box">
                    <p>AI belum membuat tugas karena ada informasi yang perlu dipastikan:</p>
                    <ul>{aiDraft.clarification_questions.map((question) => <li key={question}>{question}</li>)}</ul>
                    <p className="clarification-hint">Tambahkan jawabannya pada instruksi di atas, lalu buat draft lagi.</p>
                  </div>
                ) : (
                  <>
                    <div className="ai-draft-fields">
                      <label>Nama tugas
                        <input name="title" value={aiDraft.title || ""} onChange={updateAiDraft} maxLength={200} required />
                      </label>
                      <label>Catatan
                        <textarea name="notes" value={aiDraft.notes || ""} onChange={updateAiDraft} rows={2} maxLength={5000} />
                      </label>
                      <div className="ai-draft-dates">
                        <label>Tenggat tugas
                          <input name="due_at" type="datetime-local" value={localDateTimeValue(aiDraft.due_at)} onChange={(event) => setAiDraft({ ...aiDraft, due_at: event.target.value ? new Date(event.target.value).toISOString() : null })} />
                        </label>
                        <label>Ingatkan pada
                          <input name="reminder_at" type="datetime-local" value={localDateTimeValue(aiDraft.reminder_at)} onChange={(event) => setAiDraft({ ...aiDraft, reminder_at: event.target.value ? new Date(event.target.value).toISOString() : null })} />
                        </label>
                      </div>
                    </div>
                    <div className="ai-draft-actions">
                      <span>Belum tersimpan sampai lo konfirmasi.</span>
                      <button className="submit-button" type="button" onClick={confirmAiDraft} disabled={saving || !aiDraft.title?.trim()}>
                        {saving ? "Menyimpan..." : "Konfirmasi & buat tugas"}
                        {!saving && <span>✓</span>}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </section>
          )}

          {activePage === "agent" && (
            <>
          <div className="page-heading agent-page-heading">
            <div>
              <div className="eyebrow">PROJECT CODING WORKSPACE</div>
              <h1>Bangun sesuatu yang lebih baik.</h1>
              <p>Diskusikan perubahan dengan AI, tinjau diff, lalu setujui sebelum diterapkan.</p>
            </div>
            <div className="agent-security-pill"><i /> Perubahan selalu perlu persetujuan</div>
          </div>
          <section className="coding-agent-card">
            <div className="coding-agent-heading">
              <span className="ai-planner-icon">⌘</span>
              <div>
                <h2>Coding agent · workspace ini</h2>
                <p>Pilih satu file, jelaskan perubahan, lalu tinjau diff sebelum file disentuh.</p>
              </div>
              <span className="approval-badge">Persetujuan manual</span>
            </div>
            <form className="coding-agent-form" onSubmit={createCodeProposal}>
              <label htmlFor="agent-instruction">Apa yang ingin diubah?</label>
              <textarea
                id="agent-instruction"
                value={agentInstruction}
                onChange={(event) => setAgentInstruction(event.target.value)}
                placeholder="Contoh: Tambahkan validasi agar judul todo tidak boleh hanya berisi spasi."
                rows={2}
                maxLength={2000}
                required
              />
              <div className="agent-form-row">
                <label htmlFor="agent-file">File target
                  <select
                    id="agent-file"
                    value={agentFilePath}
                    onChange={(event) => setAgentFilePath(event.target.value)}
                    required
                  >
                    {agentFiles.map((file) => (
                      <option key={file.path} value={file.path}>{file.path}</option>
                    ))}
                  </select>
                </label>
                <button
                  className="submit-button"
                  type="submit"
                  disabled={agentLoading || !agentFilePath || agentInstruction.trim().length < 8 || !agentConsent}
                >
                  {agentLoading ? "Menyusun patch..." : "Usulkan patch"}
                  {!agentLoading && <span>→</span>}
                </button>
              </div>
              <label className="agent-consent">
                <input
                  type="checkbox"
                  checked={agentConsent}
                  onChange={(event) => setAgentConsent(event.target.checked)}
                />
                Saya setuju mengirim isi file terpilih ke provider AI yang dikonfigurasi untuk membuat proposal.
              </label>
              <p className="ai-privacy-note">
                File `.env`, database, dependency/build folders, dan file dengan pola credential umum dikecualikan.
                Satu request hanya membaca satu file. AI tidak menjalankan command atau mengubah file langsung.
              </p>
            </form>

            {agentProposal && (
              <div className="proposal-review">
                <div className="proposal-title">
                  <div>
                    <span className="eyebrow">PROPOSAL #{agentProposal.id} · {agentProposal.status}</span>
                    <h3>{agentProposal.file_path}</h3>
                    <p>{agentProposal.summary}</p>
                  </div>
                  <span className="ai-model-label">Review wajib</span>
                </div>
                <pre className="proposal-diff">{agentProposal.diff || "Tidak ada diff."}</pre>
                {agentProposal.status === "pending" ? (
                  <div className="proposal-actions">
                    <span>Periksa seluruh diff sebelum menerapkan.</span>
                    <div>
                      <button className="cancel-button" type="button" onClick={() => reviewCodeProposal("reject")} disabled={agentLoading}>Tolak</button>
                      <button className="submit-button" type="button" onClick={() => reviewCodeProposal("approve")} disabled={agentLoading}>
                        Terapkan patch
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="proposal-actions">
                    <span>{agentProposal.status === "applied" ? "Patch sudah diterapkan." : "Proposal ditolak."}</span>
                    {agentProposal.status === "applied" && (
                      <button className="cancel-button" type="button" onClick={runBackendTests} disabled={commandRunning}>
                        {commandRunning ? "Menjalankan test..." : "Jalankan backend tests"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}

            {commandResult && (
              <div className={`command-result ${commandResult.exit_code === 0 && !commandResult.timed_out ? "passed" : "failed"}`}>
                <strong>
                  {commandResult.timed_out
                    ? "Test timeout"
                    : commandResult.exit_code === 0
                      ? "Backend tests lulus"
                      : `Backend tests gagal (exit ${commandResult.exit_code})`}
                </strong>
                <code>{commandResult.command.join(" ")}</code>
                <pre>{commandResult.output || "Tidak ada output."}</pre>
              </div>
            )}
          </section>
            </>
          )}

          {activePage === "security" && (
            <section className="security-page">
              <div className="page-heading agent-page-heading">
                <div>
                  <div className="eyebrow">DEFENSIVE SECURITY CHECKS</div>
                  <h1>Periksa security project & website.</h1>
                  <p>Scan lokal tanpa network atau pemeriksaan pasif satu host berizin. Tidak menjalankan exploit atau mengirim source ke AI.</p>
                </div>
                <button
                  className="submit-button security-scan-button"
                  type="button"
                  onClick={runSecurityScan}
                  disabled={securityScanLoading}
                >
                  {securityScanLoading ? "Memeriksa project..." : "Jalankan pemeriksaan"}
                  {!securityScanLoading && <span>→</span>}
                </button>
              </div>
              <div className="security-scope-card">
                <span>⬡</span>
                <div>
                  <strong>Scope: source dan konfigurasi project ini</strong>
                  <p>Read-only · tanpa network · tanpa eksploitasi · tanpa perubahan file</p>
                </div>
              </div>
              <section className="website-security-card">
                <div className="section-heading">
                  <div>
                    <h2>Pemeriksaan website berizin</h2>
                    <p>Satu request HTTPS ke URL dan path yang dimasukkan untuk melihat TLS dan security headers. Query dan fragment tidak dikirim; tidak ada crawl atau exploit. Gunakan path read-only yang kamu berwenang periksa.</p>
                  </div>
                  <span className="approval-badge">Allowlist + konfirmasi</span>
                </div>
                <form className="website-security-form" onSubmit={runWebsiteSecurityCheck}>
                  <label htmlFor="website-security-url">URL website yang diizinkan
                    <input
                      id="website-security-url"
                      type="text"
                      value={websiteSecurityUrl}
                      onChange={(event) => setWebsiteSecurityUrl(event.target.value)}
                      placeholder="contoh: https://example.com/account"
                      autoComplete="url"
                      maxLength={2048}
                      required
                    />
                  </label>
                  <label className="agent-consent">
                    <input
                      type="checkbox"
                      checked={websiteSecurityAuthorized}
                      onChange={(event) => setWebsiteSecurityAuthorized(event.target.checked)}
                    />
                    Saya pemilik atau memiliki izin eksplisit untuk memeriksa website ini.
                  </label>
                  <button
                    className="submit-button security-scan-button"
                    type="submit"
                    disabled={websiteSecurityLoading || !websiteSecurityAuthorized || !websiteSecurityUrl.trim()}
                  >
                    {websiteSecurityLoading ? "Memeriksa host..." : "Periksa website"}
                    {!websiteSecurityLoading && <span>→</span>}
                  </button>
                </form>
                <p className="website-security-setup">
                  Host URL harus tercantum di <code>SECURITY_AUDIT_ALLOWED_HOSTS</code> pada `.env`. Path URL ikut diperiksa; query dan fragment tidak.
                  Pisahkan beberapa host dengan koma.
                </p>
                {websiteSecurityCheck && (
                  <div className="website-security-results">
                    <div className="section-heading">
                      <div>
                        <h3>{websiteSecurityCheck.host}{websiteSecurityCheck.target_path}</h3>
                        <p>
                          HTTPS terverifikasi · HTTP {websiteSecurityCheck.status_code} ·
                          {" "}{new Date(websiteSecurityCheck.checked_at).toLocaleString("id-ID")}
                        </p>
                      </div>
                    </div>
                    <ul>
                      {websiteSecurityCheck.findings.map((finding) => (
                        <li className={`website-header-check ${finding.status}`} key={finding.header}>
                          <div>
                            <strong>{finding.header}</strong>
                            <span>{finding.status === "present" ? "Terdeteksi" : "Tidak terdeteksi"}</span>
                          </div>
                          <p>{finding.recommendation}</p>
                        </li>
                      ))}
                    </ul>
                    <div className="security-limitations">
                      <strong>Batas pemeriksaan</strong>
                      <ul>{websiteSecurityCheck.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                    </div>
                  </div>
                )}
              </section>
              <section className="dependency-audit-card">
                <div className="section-heading">
                  <div>
                    <h2>Audit kerentanan dependency</h2>
                    <p>Mencocokkan versi paket frontend dan backend dengan advisory npm/PyPI. Tidak menjalankan exploit atau mengubah dependency.</p>
                  </div>
                  <button
                    className="submit-button security-scan-button"
                    type="button"
                    onClick={runDependencyAudit}
                    disabled={dependencyAuditLoading}
                  >
                    {dependencyAuditLoading ? "Mencocokkan advisory..." : "Audit dependency"}
                    {!dependencyAuditLoading && <span>→</span>}
                  </button>
                </div>
                <p className="website-security-setup">
                  Perlu `pip-audit` dari `requirements-dev.txt` dan koneksi internet. Dengan persetujuanmu, hanya nama dan versi paket yang dikirim ke layanan advisory.
                </p>
                {dependencyAudit && (
                  <div className="dependency-audit-results">
                    <div className="dependency-audit-summary">
                      <article><span>npm · paket terdampak</span><strong>{dependencyAudit.npm.affected_packages}</strong><small>{dependencyAudit.npm.packages_scanned} paket diperiksa</small></article>
                      <article><span>PyPI · paket terdampak</span><strong>{dependencyAudit.pypi.affected_packages}</strong><small>{dependencyAudit.pypi.packages_scanned} paket diperiksa</small></article>
                    </div>
                    {dependencyAudit.npm.findings.length || dependencyAudit.pypi.findings.length ? (
                      <div className="dependency-finding-list">
                        {[...dependencyAudit.npm.findings, ...dependencyAudit.pypi.findings].map((finding, index) => (
                          <article className={`dependency-finding severity-${finding.severity}`} key={`${finding.ecosystem}-${finding.package}-${finding.title}-${index}`}>
                            <div>
                              <strong>{finding.package}@{finding.installed_version}</strong>
                              <span>{finding.ecosystem} · {finding.severity}</span>
                            </div>
                            <p>{finding.title}</p>
                            {finding.advisory_ids.length > 0 && <small>Advisory: {finding.advisory_ids.join(", ")}</small>}
                            <small>{finding.fixed_versions.length > 0
                              ? `Versi perbaikan yang dilaporkan: ${finding.fixed_versions.join(", ")}`
                              : "Versi perbaikan belum tersedia di hasil advisory."}</small>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="security-empty">
                        <span>✓</span><strong>Tidak ada advisory yang cocok</strong>
                        <p>Hasil bersih bukan jaminan semua dependency aman atau bebas dari celah.</p>
                      </div>
                    )}
                    <div className="security-limitations">
                      <strong>Batas audit</strong>
                      <ul>{dependencyAudit.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                    </div>
                  </div>
                )}
              </section>
              {securityScan && (
                <>
                  <div className="security-summary">
                    <article><span>File diperiksa</span><strong>{securityScan.scanned_files}</strong></article>
                    <article className={securityScan.high_count ? "has-findings" : ""}><span>Perlu perhatian tinggi</span><strong>{securityScan.high_count}</strong></article>
                    <article className={securityScan.medium_count ? "has-findings" : ""}><span>Perlu review</span><strong>{securityScan.medium_count}</strong></article>
                    <article><span>Rendah</span><strong>{securityScan.low_count}</strong></article>
                  </div>
                  <div className="security-results">
                    <div className="section-heading">
                      <div>
                        <h2>Hasil pemeriksaan</h2>
                        <p>{securityScan.findings.length
                          ? "Sinyal statis ini perlu ditinjau manual; bukan bukti eksploitasi."
                          : "Tidak ada pola yang terdeteksi oleh pemeriksaan dasar ini."}</p>
                      </div>
                    </div>
                    {securityScan.findings.length ? (
                      <div className="security-finding-list">
                        {securityScan.findings.map((finding, index) => (
                          <article className={`security-finding severity-${finding.severity}`} key={`${finding.rule_id}-${finding.file_path}-${finding.line}-${index}`}>
                            <div className="finding-severity">{finding.severity}</div>
                            <div>
                              <h3>{finding.title}</h3>
                              <code>{finding.file_path}:{finding.line}</code>
                              <p>{finding.description}</p>
                              <small><strong>Rekomendasi:</strong> {finding.recommendation}</small>
                            </div>
                            <span className="finding-confidence">{finding.confidence}</span>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="security-empty">
                        <span>✓</span><strong>Belum ada pola berisiko yang terdeteksi</strong>
                        <p>Hasil bersih bukan jaminan project bebas kerentanan.</p>
                      </div>
                    )}
                    <div className="security-limitations">
                      <strong>Batas pemeriksaan</strong>
                      <ul>{securityScan.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
                      {securityScan.skipped_files > 0 && <small>{securityScan.skipped_files} file dilewati, termasuk file sensitif, terlalu besar, atau tidak terbaca.</small>}
                    </div>
                  </div>
                </>
              )}
              {!securityScan && !securityScanLoading && (
                <div className="security-empty first-run">
                  <span>⌕</span>
                  <strong>Belum ada pemeriksaan</strong>
                  <p>Jalankan untuk memeriksa pola konfigurasi dan source yang umum berisiko.</p>
                </div>
              )}
            </section>
          )}

          {activePage === "tasks" && (
          <>
          <section className="project-manager-card">
            <div className="section-heading">
              <div>
                <h2>Project</h2>
                <p>Kelompokkan tugas berdasarkan pekerjaan yang sedang berjalan.</p>
              </div>
            </div>
            <form className="project-create-form" onSubmit={createProject}>
              <input
                aria-label="Nama project baru"
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                placeholder="Contoh: Website kampus"
                maxLength={100}
                required
              />
              <button className="submit-button" type="submit" disabled={projectSaving}>
                {projectSaving ? "Membuat..." : "Buat project"}
              </button>
            </form>
            <div className="project-list">
              <button
                type="button"
                className={`project-chip ${projectFilter === "all" ? "selected" : ""}`}
                onClick={() => setProjectFilter("all")}
              >Semua tugas</button>
              {projects.map((project) => (
                <div className="project-chip-wrap" key={project.id}>
                  <button
                    type="button"
                    className={`project-chip ${projectFilter === String(project.id) ? "selected" : ""}`}
                    onClick={() => setProjectFilter(String(project.id))}
                  >{project.name}</button>
                  <button type="button" onClick={() => renameProject(project)} aria-label={`Ubah nama ${project.name}`} title="Ubah nama">✎</button>
                  <button type="button" onClick={() => deleteProject(project)} aria-label={`Hapus ${project.name}`} title="Hapus">×</button>
                </div>
              ))}
              <button
                type="button"
                className={`project-chip ${projectFilter === "none" ? "selected" : ""}`}
                onClick={() => setProjectFilter("none")}
              >Tanpa project</button>
            </div>
          </section>
          <div className="workspace-grid">
            <section className="task-section">
              <div className="section-heading">
                <div>
                  <h2>Daftar tugas</h2>
                  <p>Atur langkah berikutnya, tanpa kehilangan konteks.</p>
                </div>
                <div className="filter-tabs" role="tablist" aria-label="Filter tugas">
                  {[
                    ["all", "Semua"],
                    ["pending", "Aktif"],
                    ["completed", "Selesai"],
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      className={filter === value ? "selected" : ""}
                      onClick={() => setFilter(value)}
                      role="tab"
                      aria-selected={filter === value}
                      type="button"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="task-filter-controls">
                <input
                  type="search"
                  aria-label="Cari tugas"
                  placeholder="Cari nama atau catatan tugas"
                  value={taskSearch}
                  onChange={(event) => setTaskSearch(event.target.value)}
                />
                <select aria-label="Filter project" value={projectFilter} onChange={(event) => setProjectFilter(event.target.value)}>
                  <option value="all">Semua project</option>
                  <option value="none">Tanpa project</option>
                  {projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}
                </select>
                <select aria-label="Filter prioritas" value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>
                  <option value="all">Semua prioritas</option>
                  <option value="high">Tinggi</option>
                  <option value="normal">Normal</option>
                  <option value="low">Rendah</option>
                </select>
                <select aria-label="Filter tenggat" value={dueFilter} onChange={(event) => setDueFilter(event.target.value)}>
                  <option value="all">Semua tenggat</option>
                  <option value="overdue">Terlambat</option>
                  <option value="scheduled">Ada tenggat</option>
                  <option value="unscheduled">Tanpa tenggat</option>
                </select>
              </div>

              <div className="task-list">
                {loading ? (
                  <div className="empty-state"><span className="spinner" />Memuat tugas...</div>
                ) : visibleTodos.length ? (
                  visibleTodos.map((todo) => (
                    <article className={`task-row ${todo.status === "completed" ? "is-complete" : ""}`} key={todo.id}>
                      <button
                        className="check-button"
                        type="button"
                        onClick={() => toggleTodo(todo)}
                        aria-label={todo.status === "completed" ? "Tandai belum selesai" : "Tandai selesai"}
                      >
                        {todo.status === "completed" && "✓"}
                      </button>
                      <div className="task-copy">
                        <h3>{todo.title}</h3>
                        {todo.notes && <p>{todo.notes}</p>}
                        <div className="task-metadata">
                          <span className={`priority-label priority-${todo.priority || "normal"}`}>
                            Prioritas {todo.priority === "high" ? "tinggi" : todo.priority === "low" ? "rendah" : "normal"}
                          </span>
                          {todo.project_id && <span>{projects.find((project) => project.id === todo.project_id)?.name}</span>}
                        </div>
                        {todo.due_at && (
                          <div className={`due-label ${isOverdue(todo) ? "overdue" : ""}`}>
                            <span>◷</span> Tenggat {formatDue(todo.due_at)}
                            {isOverdue(todo) && <b>Terlambat</b>}
                          </div>
                        )}
                        {todo.reminder_at && (
                          <div className="due-label reminder-detail">
                            <span>♧</span> Pengingat {formatDue(todo.reminder_at)}
                            {todo.reminder_sent_at && <b>Terkirim</b>}
                          </div>
                        )}
                      </div>
                      <div className="task-actions">
                        <button type="button" onClick={() => editTodo(todo)} aria-label="Edit tugas" title="Edit">✎</button>
                        <button type="button" onClick={() => deleteTodo(todo)} aria-label="Hapus tugas" title="Hapus">×</button>
                      </div>
                    </article>
                  ))
                ) : (
                  <div className="empty-state">
                    <span className="empty-icon">{filter === "completed" ? "✓" : "✳"}</span>
                    <strong>{filter === "completed" ? "Belum ada yang selesai" : "Belum ada tugas di sini"}</strong>
                    <span>{filter === "completed" ? "Tugas yang dituntaskan akan muncul di sini." : "Tambahkan tugas pertama lo lewat form di samping."}</span>
                  </div>
                )}
              </div>
            </section>

            <aside className="composer-card">
              <div className="composer-heading">
                <span className="composer-icon">{editingId ? "✎" : "+"}</span>
                <div>
                  <h2>{editingId ? "Edit tugas" : "Tugas baru"}</h2>
                  <p>{editingId ? "Perbarui detail tugas." : "Mulai dari satu hal yang ingin dibereskan."}</p>
                </div>
              </div>
              <form onSubmit={saveTodo}>
                <label htmlFor="task-title">Nama tugas <span>*</span></label>
                <input
                  id="task-title"
                  name="title"
                  value={form.title}
                  onChange={updateForm}
                  placeholder="Contoh: Kirim proposal ke tim"
                  maxLength={200}
                  required
                />
                <label htmlFor="task-notes">Catatan <small>OPSIONAL</small></label>
                <textarea
                  id="task-notes"
                  name="notes"
                  value={form.notes}
                  onChange={updateForm}
                  placeholder="Tambahkan konteks atau langkah kecil..."
                  rows={3}
                  maxLength={5000}
                />
                <label htmlFor="task-project">Project <small>OPSIONAL</small></label>
                <select id="task-project" name="project_id" value={form.project_id} onChange={updateForm}>
                  <option value="">Tanpa project</option>
                  {projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}
                </select>
                <label htmlFor="task-priority">Prioritas</label>
                <select id="task-priority" name="priority" value={form.priority} onChange={updateForm}>
                  <option value="high">Tinggi</option>
                  <option value="normal">Normal</option>
                  <option value="low">Rendah</option>
                </select>
                <label htmlFor="task-due">Tenggat tugas <small>OPSIONAL</small></label>
                <input
                  id="task-due"
                  name="due_at"
                  type="datetime-local"
                  value={form.due_at}
                  onChange={updateForm}
                />
                <label htmlFor="task-reminder">Ingatkan pada <small>OPSIONAL</small></label>
                <input
                  id="task-reminder"
                  name="reminder_at"
                  type="datetime-local"
                  value={form.reminder_at}
                  onChange={updateForm}
                />
                <p className="form-hint">Waktu mengikuti zona waktu perangkat lo.</p>
                <div className="form-actions">
                  {editingId && <button className="cancel-button" type="button" onClick={resetForm}>Batal</button>}
                  <button className="submit-button" type="submit" disabled={saving}>
                    {saving ? "Menyimpan..." : editingId ? "Simpan perubahan" : "Tambah tugas"}
                    {!saving && <span>→</span>}
                  </button>
                </div>
              </form>
            </aside>
          </div>
          </>
          )}

          {activePage !== "chat" && (
          <footer className="page-footer">
            <span><i className="status-dot" /> Semua perubahan tersimpan otomatis</span>
            <span>Digital Operator <b>·</b> Personal workspace</span>
          </footer>
          )}
        </div>
      </section>
    </main>
  );
}
