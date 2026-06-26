import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  UploadCloud, 
  Trash2, 
  Tv, 
  LogOut, 
  RefreshCw, 
  User, 
  AlertCircle, 
  CheckCircle2, 
  Play, 
  Info,
  Activity
} from 'lucide-react';
import api from '../services/api';

export default function Dashboard() {
  const [matches, setMatches] = useState([]);
  const [title, setTitle] = useState('');
  const [file, setFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [username, setUsername] = useState('User');
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  // Load matches
  const fetchMatches = async () => {
    try {
      const response = await api.get('/api/matches/');
      setMatches(response.data);
    } catch (err) {
      console.error('Failed to load matches', err);
    }
  };

  useEffect(() => {
    fetchMatches();
    const storedUser = localStorage.getItem('username');
    if (storedUser) {
      setUsername(storedUser);
    }
  }, []);

  // Poll status of processing matches
  useEffect(() => {
    const processingMatches = matches.filter(
      (m) => m.status === 'processing' || m.status === 'pending'
    );

    if (processingMatches.length === 0) return;

    const interval = setInterval(async () => {
      let updated = false;
      const updatedMatches = await Promise.all(
        matches.map(async (match) => {
          if (match.status === 'processing' || match.status === 'pending') {
            try {
              const res = await api.get(`/api/matches/${match.id}/status/`);
              if (res.data.status !== match.status) {
                updated = true;
                return { 
                  ...match, 
                  status: res.data.status,
                  error_log: res.data.error_log 
                };
              }
            } catch (err) {
              console.error(`Error polling status for match ${match.id}`, err);
            }
          }
          return match;
        })
      );

      if (updated) {
        setMatches(updatedMatches);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [matches]);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    navigate('/login');
  };

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected && selected.type === 'video/mp4') {
      setFile(selected);
      setUploadError('');
      if (!title) {
        // Auto fill title with file name without extension
        setTitle(selected.name.replace(/\.[^/.]+$/, ""));
      }
    } else {
      setFile(null);
      setUploadError('Only MP4 video files are supported.');
    }
  };

  const handleUploadSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setUploadError('Please select a video file.');
      return;
    }
    if (!title.trim()) {
      setUploadError('Please specify a match title.');
      return;
    }

    setUploading(true);
    setUploadProgress(0);
    setUploadError('');

    const formData = new FormData();
    formData.append('title', title);
    formData.append('video_file', file);

    try {
      await api.post('/api/matches/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setUploadProgress(percentCompleted);
        },
      });

      setTitle('');
      setFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      fetchMatches();
    } catch (err) {
      console.error(err);
      setUploadError(
        err.response?.data?.detail || 
        err.response?.data?.video_file?.[0] || 
        err.response?.data?.title?.[0] || 
        'Failed to upload video. Please try again.'
      );
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteMatch = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this match analysis? This will remove all associated tracking coordinates.')) {
      return;
    }

    try {
      await api.delete(`/api/matches/${id}/`);
      setMatches(matches.filter((m) => m.id !== id));
    } catch (err) {
      console.error(`Failed to delete match ${id}`, err);
      alert('Failed to delete match.');
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header className="navbar">
        <div className="nav-brand">
          <Activity size={24} className="glow-text-cyan" />
          <span>MIAS TRACKING APP</span>
        </div>
        <div className="nav-actions">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-text-muted)' }}>
            <User size={18} />
            <span style={{ fontWeight: 500, color: 'var(--color-text)' }}>{username}</span>
          </div>
          <button onClick={handleLogout} className="btn btn-outline" style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}>
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </header>

      <main className="container" style={{ gap: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '2rem', margin: '0', textAlign: 'left' }}>Dashboard</h1>
            <p style={{ color: 'var(--color-text-muted)', textAlign: 'left', marginTop: '0.25rem' }}>
              Upload match broadcast videos to extract tracking data and events.
            </p>
          </div>
          <button onClick={fetchMatches} className="btn btn-outline" style={{ height: '2.5rem' }}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        {/* Upload Container */}
        <div className="glass-container" style={{ padding: '2rem', textAlign: 'left' }}>
          <h2 style={{ fontSize: '1.25rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <UploadCloud size={20} color="var(--color-secondary)" />
            Analyze New Match Video
          </h2>
          
          {uploadError && (
            <div className="alert alert-error">
              <AlertCircle size={18} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>{uploadError}</div>
            </div>
          )}

          <form onSubmit={handleUploadSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', alignItems: 'end' }}>
            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label" htmlFor="match-title">Match Title</label>
              <input
                id="match-title"
                type="text"
                className="input-field"
                placeholder="e.g., Chelsea vs Real Madrid - First Half"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                disabled={uploading}
              />
            </div>

            <div className="input-group" style={{ marginBottom: 0 }}>
              <label className="input-label">Select Video File (.mp4)</label>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <input
                  type="file"
                  accept="video/mp4"
                  onChange={handleFileChange}
                  ref={fileInputRef}
                  required
                  disabled={uploading}
                  style={{ display: 'none' }}
                  id="video-file-input"
                />
                <label 
                  htmlFor="video-file-input" 
                  className="input-field" 
                  style={{ 
                    cursor: uploading ? 'not-allowed' : 'pointer', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}
                >
                  <span style={{ color: file ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                    {file ? file.name : 'Choose file...'}
                  </span>
                  <UploadCloud size={16} style={{ color: 'var(--color-text-muted)' }} />
                </label>
                
                <button 
                  type="submit" 
                  className="btn btn-secondary" 
                  disabled={uploading || !file || !title.trim()}
                  style={{ whiteSpace: 'nowrap', height: '2.8rem' }}
                >
                  {uploading ? 'Uploading...' : 'Process Video'}
                </button>
              </div>
            </div>
          </form>

          {uploading && (
            <div style={{ marginTop: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                <span>Uploading match data...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="progress-bar-container">
                <div className="progress-bar-fill" style={{ width: `${uploadProgress}%` }}></div>
              </div>
            </div>
          )}
        </div>

        {/* Matches Grid */}
        <div>
          <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem', textAlign: 'left' }}>Analyses</h2>
          {matches.length === 0 ? (
            <div className="glass-container animate-pulse" style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
              <Tv size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
              <p style={{ fontSize: '1.1rem' }}>No matches uploaded yet.</p>
              <p style={{ fontSize: '0.9rem', marginTop: '0.25rem' }}>Upload your first match above to see the data and playbacks.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '1.5rem' }}>
              {matches.map((match) => (
                <div key={match.id} className="glass-container glass-card" style={{ display: 'flex', flexDirection: 'column', height: '100%', textAlign: 'left', cursor: match.status === 'completed' ? 'pointer' : 'default' }} onClick={() => match.status === 'completed' && navigate(`/matches/${match.id}`)}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '1rem' }}>
                    <span className={`badge badge-${match.status}`}>
                      {match.status}
                    </span>
                    <button 
                      onClick={(e) => handleDeleteMatch(match.id, e)} 
                      className="btn btn-outline" 
                      style={{ 
                        padding: '0.35rem', 
                        borderRadius: '6px', 
                        color: '#EF4444', 
                        borderColor: 'transparent',
                        background: 'transparent' 
                      }}
                      title="Delete Analysis"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  <h3 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.5rem', color: '#FFFFFF' }}>{match.title}</h3>
                  <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem', marginBottom: '1.5rem' }}>
                    Uploaded {formatDate(match.created_at)}
                  </p>

                  <div style={{ marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    {match.status === 'completed' ? (
                      <span style={{ 
                        color: 'var(--color-primary)', 
                        fontSize: '0.9rem', 
                        fontWeight: 600, 
                        display: 'flex', 
                        alignItems: 'center', 
                        gap: '0.25rem' 
                      }}>
                        <CheckCircle2 size={16} /> Ready for Visualization
                      </span>
                    ) : match.status === 'processing' ? (
                      <span style={{ 
                        color: 'var(--color-secondary)', 
                        fontSize: '0.9rem', 
                        fontWeight: 500,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem'
                      }}>
                        <span className="animate-spin" style={{ 
                          width: '14px', 
                          height: '14px', 
                          border: '2px solid transparent', 
                          borderTopColor: 'var(--color-secondary)', 
                          borderRadius: '50%',
                          display: 'inline-block'
                        }}></span>
                        AI Engine Processing...
                      </span>
                    ) : match.status === 'failed' ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', width: '100%' }}>
                        <span style={{ color: '#F43F5E', fontSize: '0.9rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <AlertCircle size={16} /> CV Task Failed
                        </span>
                        {match.error_log && (
                          <div style={{ 
                            fontSize: '0.75rem', 
                            background: 'rgba(244, 63, 94, 0.08)', 
                            border: '1px solid rgba(244, 63, 94, 0.2)', 
                            padding: '0.5rem', 
                            borderRadius: '4px',
                            color: '#FB7185',
                            maxHeight: '60px',
                            overflowY: 'auto',
                            fontFamily: 'monospace'
                          }}>
                            {match.error_log.substring(0, 300)}...
                          </div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                        Queued...
                      </span>
                    )}

                    {match.status === 'completed' && (
                      <div style={{
                        background: 'var(--color-primary)',
                        padding: '0.5rem',
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#FFF',
                        boxShadow: 'var(--shadow-glow-emerald)',
                        transition: 'transform 0.2s',
                      }}
                      className="play-icon"
                      >
                        <Play size={16} fill="currentColor" />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
