export interface UserRecord {
  id: string;
  username: string;
  role: "admin" | "operator" | "viewer";
  email: string | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  data: UserRecord[];
  metadata: { page: number; per_page: number; total: number };
}
