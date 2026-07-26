/**
 * ProfileSettings — Allows the user to view and edit their Lifestyle_Profile.
 * Accessible from SettingsPage.
 * On save: PUT /api/profile → shows success confirmation, weights recomputed in background.
 * Requirements: 15.5, 15.6
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

type EmploymentStatus = 'student' | 'working' | 'both';
type CommuteMethod = 'public_transit' | 'own_vehicle' | 'walking_biking' | 'none_remote';
type VehicleType = 'motorcycle' | 'car';

interface EmploymentOption {
  value: EmploymentStatus;
  label: string;
}

interface CommuteOption {
  value: CommuteMethod;
  label: string;
}

interface VehicleOption {
  value: VehicleType;
  label: string;
}

const EMPLOYMENT_OPTIONS: EmploymentOption[] = [
  { value: 'student', label: 'Student' },
  { value: 'working', label: 'Working' },
  { value: 'both', label: 'Both' },
];

const COMMUTE_OPTIONS: CommuteOption[] = [
  { value: 'public_transit', label: 'Public Transit' },
  { value: 'own_vehicle', label: 'Own Vehicle' },
  { value: 'walking_biking', label: 'Walking/Biking' },
  { value: 'none_remote', label: 'None/Remote' },
];

const VEHICLE_OPTIONS: VehicleOption[] = [
  { value: 'motorcycle', label: 'Motorcycle' },
  { value: 'car', label: 'Car' },
];

export default function ProfileSettings() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [employmentStatus, setEmploymentStatus] = useState<EmploymentStatus | null>(null);
  const [commuteMethod, setCommuteMethod] = useState<CommuteMethod | null>(null);
  const [vehicleType, setVehicleType] = useState<VehicleType | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchProfile() {
      try {
        const response = await axios.get(`${API_BASE}/api/profile`);
        const profile = response.data;
        setEmploymentStatus(profile.employment_status ?? null);
        setCommuteMethod(profile.commute_method ?? null);
        setVehicleType(profile.vehicle_type ?? null);
      } catch {
        setLoadError('Failed to load your profile. Please try again.');
      } finally {
        setLoading(false);
      }
    }
    fetchProfile();
  }, []);

  const showVehicleType = commuteMethod === 'own_vehicle';
  const isFormValid =
    employmentStatus !== null &&
    commuteMethod !== null &&
    (!showVehicleType || vehicleType !== null);

  function handleCommuteChange(method: CommuteMethod) {
    setCommuteMethod(method);
    if (method !== 'own_vehicle') {
      setVehicleType(null);
    }
  }

  async function handleSave() {
    if (!isFormValid) return;

    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await axios.put(`${API_BASE}/api/profile`, {
        employment_status: employmentStatus,
        commute_method: commuteMethod,
        vehicle_type: showVehicleType ? vehicleType : null,
      });
      setSuccess('Profile updated successfully. Budget weights are being recomputed.');
      setTimeout(() => setSuccess(null), 5000);
    } catch {
      setError('Failed to save your profile. Please try again.');
    } finally {
      setIsSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="page page-profile-settings" style={styles.container}>
        <p style={styles.loadingText}>Loading profile...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="page page-profile-settings" style={styles.container}>
        <p style={styles.errorText} role="alert">{loadError}</p>
        <button onClick={() => navigate('/settings')} style={styles.backButton} type="button">
          Back to Settings
        </button>
      </div>
    );
  }

  return (
    <div className="page page-profile-settings" style={styles.container}>
      <div style={styles.content}>
        <div style={styles.header}>
          <button
            onClick={() => navigate('/settings')}
            style={styles.backLink}
            type="button"
            aria-label="Back to settings"
          >
            ← Settings
          </button>
          <h1 style={styles.title}>Edit Profile</h1>
          <p style={styles.subtitle}>
            Update your lifestyle details to keep budget personalization accurate.
          </p>
        </div>

        {/* Employment Status */}
        <fieldset style={styles.fieldset}>
          <legend style={styles.legend}>Employment Status</legend>
          <div style={styles.radioGroup} role="radiogroup" aria-label="Employment status">
            {EMPLOYMENT_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setEmploymentStatus(option.value)}
                style={{
                  ...styles.radioButton,
                  ...(employmentStatus === option.value ? styles.radioButtonSelected : {}),
                }}
                aria-pressed={employmentStatus === option.value}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Commute Method */}
        <fieldset style={styles.fieldset}>
          <legend style={styles.legend}>Commute Method</legend>
          <div style={styles.radioGroup} role="radiogroup" aria-label="Commute method">
            {COMMUTE_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => handleCommuteChange(option.value)}
                style={{
                  ...styles.radioButton,
                  ...(commuteMethod === option.value ? styles.radioButtonSelected : {}),
                }}
                aria-pressed={commuteMethod === option.value}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </fieldset>

        {/* Vehicle Type - Conditional */}
        {showVehicleType && (
          <fieldset style={styles.fieldset}>
            <legend style={styles.legend}>Vehicle Type</legend>
            <div style={styles.radioGroup} role="radiogroup" aria-label="Vehicle type">
              {VEHICLE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setVehicleType(option.value)}
                  style={{
                    ...styles.radioButton,
                    ...(vehicleType === option.value ? styles.radioButtonSelected : {}),
                  }}
                  aria-pressed={vehicleType === option.value}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>
        )}

        {error && (
          <p style={styles.errorText} role="alert">
            {error}
          </p>
        )}

        {success && (
          <p style={styles.successText} role="status">
            {success}
          </p>
        )}

        <button
          onClick={handleSave}
          disabled={!isFormValid || isSaving}
          style={{
            ...styles.saveButton,
            ...(!isFormValid || isSaving ? styles.saveButtonDisabled : {}),
          }}
          type="button"
        >
          {isSaving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '1rem',
    minHeight: '100vh',
  },
  content: {
    width: '100%',
    maxWidth: '400px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  header: {
    width: '100%',
    marginBottom: '1.5rem',
  },
  backLink: {
    background: 'none',
    border: 'none',
    color: '#2563eb',
    fontSize: '0.875rem',
    fontWeight: '500',
    cursor: 'pointer',
    padding: 0,
    marginBottom: '0.75rem',
    display: 'inline-block',
  },
  title: {
    fontSize: '1.5rem',
    fontWeight: '700',
    marginBottom: '0.5rem',
  },
  subtitle: {
    fontSize: '0.95rem',
    color: '#666',
    lineHeight: '1.4',
  },
  fieldset: {
    width: '100%',
    border: 'none',
    padding: 0,
    margin: '0 0 1.25rem 0',
  },
  legend: {
    fontSize: '0.9rem',
    fontWeight: '600',
    marginBottom: '0.5rem',
    color: '#333',
  },
  radioGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.5rem',
  },
  radioButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0.75rem 1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    background: '#fff',
    cursor: 'pointer',
    width: '100%',
    fontSize: '0.95rem',
    fontWeight: '500',
    transition: 'border-color 0.2s, background 0.2s',
  },
  radioButtonSelected: {
    borderColor: '#2563eb',
    background: '#eff6ff',
  },
  errorText: {
    color: '#dc2626',
    fontSize: '0.875rem',
    marginTop: '0.75rem',
  },
  successText: {
    color: '#16a34a',
    fontSize: '0.875rem',
    marginTop: '0.75rem',
    fontWeight: '500',
  },
  saveButton: {
    marginTop: '1.5rem',
    width: '100%',
    padding: '0.875rem',
    fontSize: '1rem',
    fontWeight: '600',
    borderRadius: '8px',
    border: 'none',
    background: '#2563eb',
    color: '#fff',
    cursor: 'pointer',
  },
  saveButtonDisabled: {
    background: '#93c5fd',
    cursor: 'not-allowed',
  },
  loadingText: {
    fontSize: '0.95rem',
    color: '#6b7280',
    textAlign: 'center',
    marginTop: '3rem',
  },
  backButton: {
    marginTop: '1rem',
    padding: '0.75rem 1.5rem',
    fontSize: '0.9rem',
    fontWeight: '500',
    borderRadius: '8px',
    border: '1px solid #e0e0e0',
    background: '#fff',
    cursor: 'pointer',
    color: '#374151',
  },
};
