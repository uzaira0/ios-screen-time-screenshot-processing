import { useState, useEffect, useCallback } from "react";
import { Layout } from "@/components/layout/Layout";
import { useAuth, useRequireAuth } from "@/hooks/useAuth";
import { UserActivityTable } from "@/components/admin/UserActivityTable";
import { api } from "@/services/apiClient";
import toast from "react-hot-toast";
import type { components } from "@/types/api-schema";

// Use type from OpenAPI schema (Pydantic is the single source of truth)
type UserActivity = components["schemas"]["UserStatsRead"];

export const AdminPage = () => {
  useRequireAuth(); // Ensure user is logged in
  const { isAdmin } = useAuth();

  const [users, setUsers] = useState<UserActivity[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);

  const loadUsers = useCallback(async () => {
    try {
      const users = await api.admin.getUsers();
      setUsers(users ?? []);
    } catch (error) {
      console.error("Failed to load users:", error);
    } finally {
      setIsLoadingUsers(false);
    }
  }, []);

  const handleUpdateUser = async (
    userId: number,
    updates: { is_active?: boolean; role?: string },
  ) => {
    try {
      await api.admin.updateUser(userId, updates);
      toast.success("User updated successfully");
      loadUsers();
    } catch (error) {
      toast.error("Failed to update user");
      console.error("Update user error:", error);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadUsers();
    }
  }, [isAdmin, loadUsers]);

  if (!isAdmin) {
    return (
      <Layout>
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-8 text-center">
          <h2 className="text-2xl font-bold text-red-800 mb-2">
            Access Denied
          </h2>
          <p className="text-red-600">You need admin privileges to access this page</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">User Management</h1>
          <p className="text-slate-600 dark:text-slate-400 mt-2">
            Manage user accounts and permissions
          </p>
        </div>

        <UserActivityTable
          users={users}
          loading={isLoadingUsers}
          onUpdateUser={handleUpdateUser}
        />
      </div>
    </Layout>
  );
};
