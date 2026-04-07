import { useEffect } from "react";
import { useAuthStore } from "@/store/authStore";
import { useNavigate } from "react-router";
import { api } from "@/services/apiClient";
import toast from "react-hot-toast";
import { config } from "@/config";

export const useAuth = () => {
  const {
    userId,
    username,
    role,
    sitePassword,
    isAuthenticated,
    login,
    logout,
    setUserId,
    setRole,
  } = useAuthStore();

  // Always verify userId and role with server on mount
  // This handles stale cached data after database reset/migration or role changes
  // Skip in Tauri/WASM mode — no server to verify against
  useEffect(() => {
    if (config.isLocalMode) return;
    if (isAuthenticated && username) {
      api.auth
        .getMe()
        .then((user) => {
          if (user?.id && user.id !== userId) {
            if (config.isDev) {
              console.log(
                `[useAuth] Updating stale userId: ${userId} -> ${user.id}`,
              );
            }
            setUserId(user.id);
          }
          // Always update role from server (handles promotions/demotions)
          if (user?.role && user.role !== role) {
            if (config.isDev) {
              console.log(
                `[useAuth] Updating role: ${role} -> ${user.role}`,
              );
            }
            setRole(user.role);
          }
        })
        .catch((err) => {
          console.error("Failed to fetch user ID:", err);
        });
    }
  }, [isAuthenticated, username]); // Intentionally exclude userId/role to run on mount

  const isAdmin = role === "admin";

  return {
    userId,
    username,
    role,
    sitePassword,
    isAdmin,
    isAuthenticated,
    login,
    logout,
  };
};

interface UseRequireAuthOptions {
  skip?: boolean;
}

export const useRequireAuth = (options: UseRequireAuthOptions = {}) => {
  const { skip = false } = options;
  const { isAuthenticated, userId, username } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!skip && !isAuthenticated) {
      toast.error("Please login to continue");
      navigate("/login");
    }
  }, [isAuthenticated, navigate, skip]);

  return { isAuthenticated, userId, username };
};
