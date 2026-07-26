/**
 * useProfileStatus hook - Fetches profile completion status from the backend.
 * Used by ProtectedRoute to gate dashboard access until profile onboarding is complete.
 * Requirement 15.1: Gate dashboard access until profile_completed.
 */
import { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface ProfileStatus {
  profileCompleted: boolean;
  loading: boolean;
}

export function useProfileStatus(): ProfileStatus {
  const [profileCompleted, setProfileCompleted] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProfileStatus();
  }, []);

  async function fetchProfileStatus() {
    try {
      const response = await axios.get(`${API_BASE}/api/profile`);
      setProfileCompleted(response.data.profile_completed ?? false);
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        // Profile not found — not completed
        setProfileCompleted(false);
      } else {
        // Network or other error — treat as not completed for safety
        setProfileCompleted(false);
      }
    } finally {
      setLoading(false);
    }
  }

  return { profileCompleted, loading };
}
