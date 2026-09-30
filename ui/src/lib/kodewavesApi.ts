import { resolveBrowserBackendUrl } from './apiClient';

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const baseUrl = resolveBrowserBackendUrl();
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const apiPath = cleanEndpoint.startsWith('/api/v1') ? cleanEndpoint : `/api/v1${cleanEndpoint}`;
  const url = `${baseUrl}${apiPath}`;

  // Read auth token from cookies if in browser
  let authHeader = '';
  if (typeof document !== 'undefined') {
    const match = document.cookie.match(/(?:^|;\s*)kodewaves_auth_token=([^;]+)/) ||
                  document.cookie.match(/(?:^|;\s*)dograh_auth_token=([^;]+)/) ||
                  document.cookie.match(/(?:^|;\s*)oss_token=([^;]+)/);
    if (match) {
      authHeader = `Bearer ${decodeURIComponent(match[1])}`;
    }
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(authHeader ? { Authorization: authHeader } : {}),
    ...((options.headers as Record<string, string>) || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errJson = await response.json();
      if (Array.isArray(errJson.detail)) {
        errorDetail = errJson.detail
          .map((d: any) => (typeof d === "string" ? d : d.msg || `${d.loc?.join(".")}: ${d.msg}` || JSON.stringify(d)))
          .join(", ");
      } else if (typeof errJson.detail === "object" && errJson.detail !== null) {
        errorDetail = JSON.stringify(errJson.detail);
      } else {
        errorDetail = errJson.detail || errJson.message || JSON.stringify(errJson);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail || `API request failed: ${response.status}`);
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// ADMIN TYPES & APIS
// ---------------------------------------------------------------------------

export interface MasterCredential {
  id?: number;
  provider: string;
  category: 'llm' | 'stt' | 'tts' | 'sts' | 'telecom';
  display_name: string;
  api_key_masked?: string;
  api_key?: string;
  api_secret?: string;
  extra_config?: Record<string, any>;
  is_active: boolean;
  status: 'active' | 'degraded' | 'error' | 'untested';
  last_tested_at?: string;
  error_message?: string;
}

export interface ModelCatalogEntry {
  id: number;
  provider: string;
  model_id: string;
  display_name: string;
  category: 'llm' | 'stt' | 'tts' | 'sts';
  cost_per_minute: number;
  markup_margin_percent: number;
  rate_per_minute: number;
  is_active: boolean;
  is_default: boolean;
  region_or_country?: string;
  languages_supported?: string[];
  description?: string;
}

export interface AdminUserItem {
  id: number;
  email: string;
  name?: string;
  provider_id?: string;
  is_superuser: boolean;
  is_active: boolean;
  has_local_ai_access?: boolean;
  is_wallet_frozen?: boolean;
  max_concurrent_calls?: number;
  max_agents?: number;
  enable_campaigns?: boolean;
  enable_crm?: boolean;
  enable_widgets?: boolean;
  enable_appointments?: boolean;
  enable_forms?: boolean;
  enable_byok?: boolean;
  created_at?: string;
  organization_id?: number;
  organization_name?: string;
  wallet_balance_minutes?: number;
  plan_name?: string;
  total_calls?: number;
  organization?: {
    id: number;
    name?: string;
    wallet_balance_minutes?: number;
    current_plan?: string;
  };
}


export interface SaaSPlan {
  id: number;
  name: string;
  code: string;
  description?: string;
  monthly_price_inr: number;
  monthly_price_usd: number;
  included_minutes: number;
  overage_rate_per_minute: number;
  max_concurrent_calls: number;
  allow_user_byok: boolean;
  features?: string[];
  is_active: boolean;
  is_public: boolean;
}

export interface CreditPackage {
  id: number;
  name: string;
  minutes: number;
  price_inr: number;
  price_usd: number;
  bonus_minutes: number;
  is_popular: boolean;
  is_active: boolean;
}

export interface MonitoringStats {
  total_calls: number;
  active_calls: number;
  completed_calls: number;
  total_minutes: number;
  total_revenue_inr: number;
  gross_margin_percent: number;
  system_health: 'healthy' | 'degraded' | 'critical';
}

export interface LiveCallItem {
  run_id: number;
  call_sid?: string;
  agent_name: string;
  organization_name?: string;
  user_email?: string;
  provider: string;
  telecom_carrier: string;
  duration_seconds: number;
  started_at: string;
  status: 'in-progress' | 'ringing' | 'connected';
}

export interface BannedWord {
  id: number;
  keyword: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  action: 'flag' | 'terminate' | 'alert_admin';
  created_at: string;
}

export interface FlaggedViolation {
  id: number;
  workflow_run_id: number;
  organization_id: number;
  violation_type: string;
  matched_text: string;
  action_taken: string;
  created_at: string;
}

export interface PlatformSettings {
  company_name: string;
  logo_url?: string;
  support_email?: string;
  primary_color?: string;
  allow_user_byok: boolean;
  enforce_wallet_balance: boolean;
  enable_local_ai_engine?: boolean;
  local_ai_access_policy?: 'public' | 'restricted';
  ollama_endpoint?: string;
  speaches_endpoint?: string;
  local_ai_max_concurrency?: number;
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_from?: string;
}

export interface AuditLogItem {
  id: number;
  user_email?: string;
  action: string;
  target_resource: string;
  details?: Record<string, any>;
  ip_address?: string;
  created_at: string;
}

export const adminApi = {
  // Master Keys
  getMasterKeys: () => apiFetch<MasterCredential[]>('/admin/master-keys'),
  saveMasterKey: (data: Partial<MasterCredential>) =>
    apiFetch<{ message: string; id: number }>('/admin/master-keys', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  testMasterKey: (provider: string, apiKey?: string) =>
    apiFetch<{ success: boolean; message: string; latency_ms?: number }>('/admin/master-keys/test', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key: apiKey }),
    }),
  deleteMasterKey: (provider: string) =>
    apiFetch<{ message: string }>(`/admin/master-keys/${provider}`, {
      method: 'DELETE',
    }),

  // Model Catalog
  getModels: (category?: string) =>
    apiFetch<ModelCatalogEntry[]>(`/admin/models${category ? `?category=${category}` : ''}`),
  createModel: (data: Partial<ModelCatalogEntry>) =>
    apiFetch<ModelCatalogEntry>('/admin/models', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateModel: (id: number, data: Partial<ModelCatalogEntry>) =>
    apiFetch<ModelCatalogEntry>(`/admin/models/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteModel: (id: number) =>
    apiFetch<{ message: string }>(`/admin/models/${id}`, {
      method: 'DELETE',
    }),

  // Users
  getUsers: (params?: { search?: string; role?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.search) q.set('search', params.search);
    if (params?.role && params.role !== 'all') q.set('role', params.role);
    if (params?.status && params.status !== 'all') q.set('status', params.status);
    const qs = q.toString();
    return apiFetch<AdminUserItem[]>(`/admin/users${qs ? `?${qs}` : ''}`);
  },
  createUser: (data: {
    email: string;
    password: string;
    name?: string;
    is_superuser?: boolean;
    plan_code?: string;
    initial_minutes?: number;
    is_active?: boolean;
  }) =>
    apiFetch<{ message: string; user_id: number; organization_id: number }>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateUser: (
    userId: number,
    data: Record<string, any>
  ) =>
    apiFetch<{ message: string }>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  grantCredits: (userId: number, minutes: number, note?: string) =>
    apiFetch<{ message: string; new_balance: number }>(`/admin/users/${userId}/grant-credits`, {
      method: 'POST',
      body: JSON.stringify({ minutes, note }),
    }),
  updateUserStatus: (userId: number, isActive: boolean) =>
    apiFetch<{ message: string }>(`/admin/users/${userId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ is_active: isActive }),
    }),
  resetPassword: (userId: number, newPassword: string) =>
    apiFetch<{ message: string }>(`/admin/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),
  impersonateUser: (userId: number) =>
    apiFetch<{ token: string; user_id: number; email: string; redirect_url: string }>(`/admin/users/${userId}/impersonate`, {
      method: 'POST',
    }),
  deleteUser: (userId: number) =>
    apiFetch<{ message: string }>(`/admin/users/${userId}`, {
      method: 'DELETE',
    }),

  // Plans
  getPlans: () => apiFetch<SaaSPlan[]>('/admin/plans'),
  createPlan: (data: Partial<SaaSPlan>) =>
    apiFetch<SaaSPlan>('/admin/plans', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updatePlan: (id: number, data: Partial<SaaSPlan>) =>
    apiFetch<SaaSPlan>(`/admin/plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deletePlan: (id: number) =>
    apiFetch<{ message: string }>(`/admin/plans/${id}`, {
      method: 'DELETE',
    }),

  // Credit Packages
  getCreditPackages: () => apiFetch<CreditPackage[]>('/admin/credit-packages'),
  createCreditPackage: (data: Partial<CreditPackage>) =>
    apiFetch<CreditPackage>('/admin/credit-packages', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateCreditPackage: (id: number, data: Partial<CreditPackage>) =>
    apiFetch<CreditPackage>(`/admin/credit-packages/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteCreditPackage: (id: number) =>
    apiFetch<{ message: string }>(`/admin/credit-packages/${id}`, {
      method: 'DELETE',
    }),

  // Monitoring
  getStats: () => apiFetch<MonitoringStats>('/admin/monitoring/stats'),
  getLiveCalls: () => apiFetch<LiveCallItem[]>('/admin/monitoring/live-calls'),
  killCall: (runId: number, reason?: string) =>
    apiFetch<{ message: string }>('/admin/monitoring/kill-call', {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, reason }),
    }),

  // Moderation
  getBannedWords: () => apiFetch<BannedWord[]>('/admin/moderation/banned-words'),
  addBannedWord: (data: Partial<BannedWord>) =>
    apiFetch<BannedWord>('/admin/moderation/banned-words', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteBannedWord: (id: number) =>
    apiFetch<{ message: string }>(`/admin/moderation/banned-words/${id}`, {
      method: 'DELETE',
    }),
  getViolations: () => apiFetch<FlaggedViolation[]>('/admin/moderation/violations'),

  // Settings
  getSettings: () => apiFetch<PlatformSettings>('/admin/settings'),
  saveSettings: (data: Partial<PlatformSettings>) =>
    apiFetch<{ message: string }>('/admin/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Audit Logs
  getAuditLogs: () => apiFetch<AuditLogItem[]>('/admin/audit-logs'),
};

// ---------------------------------------------------------------------------
// AGENTLABS USER FEATURES APIS
// ---------------------------------------------------------------------------

export interface Contact {
  id: number;
  first_name: string;
  last_name?: string;
  phone: string;
  email?: string;
  company?: string;
  stage_id?: number;
  notes?: string;
  custom_fields?: Record<string, any>;
  created_at: string;
}

export interface LeadStage {
  id: number;
  name: string;
  order: number;
  color?: string;
}

export interface Appointment {
  id: number;
  title: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  start_time: string;
  end_time: string;
  status: 'confirmed' | 'pending' | 'cancelled' | 'completed';
  notes?: string;
}

export interface DynamicForm {
  id: number;
  title: string;
  slug: string;
  description?: string;
  fields: Array<{
    name: string;
    label: string;
    type: 'text' | 'number' | 'email' | 'phone' | 'select' | 'checkbox';
    required: boolean;
    options?: string[];
  }>;
  is_active: boolean;
  submission_count: number;
  created_at: string;
}

export interface WebsiteWidget {
  id: number;
  name: string;
  agent_id?: number;
  primary_color: string;
  position: 'bottom-right' | 'bottom-left';
  welcome_message: string;
  is_active: boolean;
  embed_code?: string;
}

export interface PromptTemplate {
  id: number;
  title: string;
  category: string;
  description?: string;
  system_prompt: string;
  first_message?: string;
  tags?: string[];
  is_featured: boolean;
}

export interface SovereignWallet {
  balance_minutes: number;
  total_credited_minutes: number;
  total_consumed_minutes: number;
  low_balance_threshold: number;
  plan_name?: string;
  plan_minutes?: number;
}

export interface WalletLedgerItem {
  id: number;
  delta_minutes: number;
  balance_after: number;
  reason: string;
  reference_id?: string;
  created_at: string;
}

export const crmApi = {
  getContacts: () => apiFetch<Contact[]>('/crm/contacts'),
  createContact: (data: Partial<Contact>) =>
    apiFetch<Contact>('/crm/contacts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateContact: (id: number, data: Partial<Contact>) =>
    apiFetch<Contact>(`/crm/contacts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteContact: (id: number) =>
    apiFetch<{ message: string }>(`/crm/contacts/${id}`, {
      method: 'DELETE',
    }),
  getStages: () => apiFetch<LeadStage[]>('/crm/stages'),
  createStage: (data: Partial<LeadStage>) =>
    apiFetch<LeadStage>('/crm/stages', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const appointmentsApi = {
  getAppointments: () => apiFetch<Appointment[]>('/appointments'),
  createAppointment: (data: Partial<Appointment>) =>
    apiFetch<Appointment>('/appointments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateAppointment: (id: number, data: Partial<Appointment>) =>
    apiFetch<Appointment>(`/appointments/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteAppointment: (id: number) =>
    apiFetch<{ message: string }>(`/appointments/${id}`, {
      method: 'DELETE',
    }),
};

export const formsApi = {
  getForms: () => apiFetch<DynamicForm[]>('/forms'),
  getForm: (id: number) => apiFetch<DynamicForm>(`/forms/${id}`),
  createForm: (data: Partial<DynamicForm>) =>
    apiFetch<DynamicForm>('/forms', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateForm: (id: number, data: Partial<DynamicForm>) =>
    apiFetch<DynamicForm>(`/forms/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteForm: (id: number) =>
    apiFetch<{ message: string }>(`/forms/${id}`, {
      method: 'DELETE',
    }),
  getSubmissions: (formId: number) =>
    apiFetch<Array<{ id: number; data: Record<string, any>; created_at: string }>>(`/forms/${formId}/submissions`),
};

export const widgetsApi = {
  getWidgets: () => apiFetch<WebsiteWidget[]>('/widgets'),
  getWidget: (id: number) => apiFetch<WebsiteWidget>(`/widgets/${id}`),
  createWidget: (data: Partial<WebsiteWidget>) =>
    apiFetch<WebsiteWidget>('/widgets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateWidget: (id: number, data: Partial<WebsiteWidget>) =>
    apiFetch<WebsiteWidget>(`/widgets/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteWidget: (id: number) =>
    apiFetch<{ message: string }>(`/widgets/${id}`, {
      method: 'DELETE',
    }),
};

export const promptTemplatesApi = {
  getTemplates: (category?: string) =>
    apiFetch<PromptTemplate[]>(`/prompt-templates${category ? `?category=${category}` : ''}`),
  createTemplate: (data: Partial<PromptTemplate>) =>
    apiFetch<PromptTemplate>('/prompt-templates', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteTemplate: (id: number) =>
    apiFetch<{ message: string }>(`/prompt-templates/${id}`, {
      method: 'DELETE',
    }),
};

export const sovereignBillingApi = {
  getWallet: () => apiFetch<SovereignWallet>('/billing-sovereign/wallet'),
  getLedger: () => apiFetch<WalletLedgerItem[]>('/billing-sovereign/ledger'),
  getPlans: () => apiFetch<SaaSPlan[]>('/billing-sovereign/plans'),
  subscribe: (planId: number) =>
    apiFetch<{ message: string; plan_id: number }>('/billing-sovereign/subscribe', {
      method: 'POST',
      body: JSON.stringify({ plan_id: planId }),
    }),
};

export const publicApi = {
  getPublicPlans: () => apiFetch<SaaSPlan[]>('/billing-sovereign/public/plans'),
  getPublicCreditPackages: () => apiFetch<CreditPackage[]>('/billing-sovereign/public/packages'),
};

export interface PaymentConfig {
  razorpay_enabled: boolean;
  razorpay_key_id?: string;
  stripe_enabled: boolean;
  stripe_publishable_key?: string;
  default_currency: string;
}

export interface CreateOrderPayload {
  package_id?: string;
  plan_id?: string;
  plan_code?: string;
  gateway?: 'razorpay' | 'stripe';
  currency?: string;
  billing_cycle?: 'monthly' | 'annual';
}

export interface CreateOrderResult {
  order_id: string;
  amount: number;
  currency: string;
  gateway: string;
  key_id?: string;
  checkout_url?: string;
  notes?: Record<string, any>;
}

export interface VerifyPaymentPayload {
  gateway: string;
  order_id: string;
  payment_id: string;
  signature?: string;
  package_id?: string;
  plan_id?: string;
  plan_code?: string;
}

export interface VerifyPaymentResult {
  success: boolean;
  message: string;
  minutes_added: number;
  new_wallet_balance: number;
  plan_code?: string;
}

export const paymentsApi = {
  getConfig: () => apiFetch<PaymentConfig>('/payments/config'),
  createOrder: (payload: CreateOrderPayload) =>
    apiFetch<CreateOrderResult>('/payments/create-order', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  verifyPayment: (payload: VerifyPaymentPayload) =>
    apiFetch<VerifyPaymentResult>('/payments/verify', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};


