import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { 
  Play, 
  Pause, 
  ArrowLeft, 
  Activity, 
  Loader2, 
  ShieldAlert, 
  Sliders, 
  Zap, 
  TrendingUp, 
  Award, 
  Clock, 
  Volume2,
  Tv,
  ChevronRight,
  User,
  Shield
} from 'lucide-react';
import api from '../services/api';
import PitchCanvas from '../components/PitchCanvas';

export default function TacticalViewer() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [match, setMatch] = useState(null);
  const [events, setEvents] = useState([]);
  const [frames, setFrames] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Playback state
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1); // multiplier: 0.25, 0.5, 1, 2, 4
  const [showLabels, setShowLabels] = useState(true);
  
  // Selected analysis states
  const [activeTab, setActiveTab] = useState('timeline'); // 'timeline' | 'stats' | 'player'
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [eventFilter, setEventFilter] = useState('all'); // 'all' | 'pass' | 'shot' | 'sprint' | 'interception'

  // Buffer state
  const [loadedRanges, setLoadedRanges] = useState([]); // array of {start, end}
  const [loadingChunk, setLoadingChunk] = useState(false);
  
  const animationRef = useRef(null);
  const lastTimeRef = useRef(null);
  const currentFrameRef = useRef(0);

  const CHUNK_SIZE = 750;

  // Frame rate is measured off the uploaded video during processing rather than assumed.
  // The animation loop reads it through a ref because the rAF callback captures its closure
  // when playback starts and would otherwise keep using the pre-load fallback.
  const fps = match?.video_fps || 20;
  const fpsRef = useRef(20);

  useEffect(() => {
    fpsRef.current = fps;
  }, [fps]);

  // Sync ref with state so requestAnimationFrame loop has current frame index
  useEffect(() => {
    currentFrameRef.current = currentFrame;
  }, [currentFrame]);

  // Load match details & events on mount
  useEffect(() => {
    const init = async () => {
      try {
        const matchRes = await api.get(`/api/matches/${id}/`);
        setMatch(matchRes.data);

        const eventsRes = await api.get(`/api/matches/${id}/events/`);
        setEvents(eventsRes.data);

        // Fetch initial frame chunk (0 to 750)
        await fetchFrames(0, CHUNK_SIZE);
        setLoading(false);
      } catch (err) {
        console.error(err);
        setError(err.response?.data?.detail || 'Failed to load tactical details.');
        setLoading(false);
      }
    };
    init();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [id]);

  // Buffer chunk fetcher
  const fetchFrames = async (start, end) => {
    // Check if range already loaded to prevent duplicate queries
    const isLoaded = loadedRanges.some(
      (r) => start >= r.start && end <= r.end
    );
    if (isLoaded) return;

    setLoadingChunk(true);
    try {
      const response = await api.get(
        `/api/matches/${id}/frames/?frame_start=${start}&frame_end=${end}`
      );
      
      // Merge new frames into state
      setFrames((prev) => ({
        ...prev,
        ...response.data,
      }));

      setLoadedRanges((prev) => [...prev, { start, end }]);
    } catch (err) {
      console.error('Failed to load frames chunk', err);
    } finally {
      setLoadingChunk(false);
    }
  };

  // Buffer monitor: fetch ahead as playback advances
  useEffect(() => {
    if (!match) return;
    const totalFrames = match.total_frames;
    
    // If we are within 250 frames of the maximum frame loaded, prefetch the next chunk
    const maxLoaded = loadedRanges.reduce((max, r) => Math.max(max, r.end), 0);
    
    if (currentFrame + 250 > maxLoaded && maxLoaded < totalFrames && !loadingChunk) {
      const nextStart = maxLoaded + 1;
      const nextEnd = Math.min(nextStart + CHUNK_SIZE - 1, totalFrames);
      fetchFrames(nextStart, nextEnd);
    }
  }, [currentFrame, loadedRanges, loadingChunk, match]);

  // Animation Loop
  const playLoop = (time) => {
    if (lastTimeRef.current !== null) {
      const delta = (time - lastTimeRef.current) / 1000; // seconds elapsed
      const framesToAdvance = delta * fpsRef.current * speed;
      const nextFrame = Math.min(
        currentFrameRef.current + framesToAdvance, 
        match?.total_frames || 0
      );

      setCurrentFrame(Math.floor(nextFrame));

      if (nextFrame >= (match?.total_frames || 0)) {
        setIsPlaying(false);
        lastTimeRef.current = null;
        return;
      }
    }
    
    lastTimeRef.current = time;
    animationRef.current = requestAnimationFrame(playLoop);
  };

  useEffect(() => {
    if (isPlaying) {
      lastTimeRef.current = null;
      animationRef.current = requestAnimationFrame(playLoop);
    } else {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      lastTimeRef.current = null;
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, speed, match]);

  // Handle manual frame scrubbing
  const handleScrubChange = (e) => {
    const frameIndex = parseInt(e.target.value, 10);
    setCurrentFrame(frameIndex);
    
    // Ensure range is loaded if user jumps ahead
    const chunkStart = Math.floor(frameIndex / CHUNK_SIZE) * CHUNK_SIZE;
    const chunkEnd = chunkStart + CHUNK_SIZE;
    fetchFrames(chunkStart, chunkEnd);
  };

  const handlePlayPause = () => {
    if (currentFrame >= (match?.total_frames || 0)) {
      setCurrentFrame(0);
    }
    setIsPlaying(!isPlaying);
  };

  // Convert frame number to match clock MM:SS
  const formatTime = (frameIndex) => {
    const seconds = Math.floor(frameIndex / fps);
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  // Seek to event frame and highlight the actor
  const handleEventClick = (event) => {
    setIsPlaying(false);
    setCurrentFrame(event.frame_number);
    
    // Pre-load the target range
    const chunkStart = Math.floor(event.frame_number / CHUNK_SIZE) * CHUNK_SIZE;
    const chunkEnd = chunkStart + CHUNK_SIZE;
    fetchFrames(chunkStart, chunkEnd);

    if (event.player_initiator !== null && event.player_initiator !== undefined) {
      // Find the player object in the clicked event
      setSelectedPlayer({
        player_id: event.player_initiator,
        team_classification: event.team || 'team_a'
      });
      setActiveTab('player');
    }
  };

  const handlePlayerSelectFromCanvas = (player) => {
    setSelectedPlayer(player);
    if (player) {
      setActiveTab('player');
    }
  };

  // Extract players & ball from current frame data
  const currentFrameRecords = frames[currentFrame] || [];
  
  const framePlayers = useMemo(() => {
    return currentFrameRecords.filter((r) => r.player_id !== -1 && r.team !== 'ball');
  }, [currentFrameRecords]);

  const frameBall = useMemo(() => {
    const ballRec = currentFrameRecords.find((r) => r.player_id === -1 || r.team === 'ball');
    if (!ballRec) return null;
    return {
      x_coord: ballRec.x,
      y_coord: ballRec.y
    };
  }, [currentFrameRecords]);

  // Group players for canvas mapping
  const mappedPlayers = useMemo(() => {
    return framePlayers.map(p => ({
      player_id: p.player_id,
      team_classification: p.team,
      x_coord: p.x,
      y_coord: p.y
    }));
  }, [framePlayers]);

  // Aggregate stats from events
  const stats = useMemo(() => {
    if (events.length === 0) return {
      possessionA: 50,
      possessionB: 50,
      passesA: 0,
      passesB: 0,
      passesSuccessA: 0,
      passesSuccessB: 0,
      shotsA: 0,
      shotsB: 0,
      sprintsA: 0,
      sprintsB: 0
    };

    let pCountA = 0;
    let pCountB = 0;
    let passA = 0, passB = 0;
    let passSuccessA = 0, passSuccessB = 0;
    let shotA = 0, shotB = 0;
    let sprintA = 0, sprintB = 0;

    events.forEach(e => {
      if (e.event_type === 'possession') {
        if (e.team === 'team_a') pCountA++;
        if (e.team === 'team_b') pCountB++;
      } else if (e.event_type === 'pass') {
        const isSuccess = e.details?.success === true;
        if (e.team === 'team_a') {
          passA++;
          if (isSuccess) passSuccessA++;
        } else if (e.team === 'team_b') {
          passB++;
          if (isSuccess) passSuccessB++;
        }
      } else if (e.event_type === 'shot') {
        if (e.team === 'team_a') shotA++;
        if (e.team === 'team_b') shotB++;
      } else if (e.event_type === 'sprint') {
        if (e.team === 'team_a') sprintA++;
        if (e.team === 'team_b') sprintB++;
      }
    });

    const totalPossession = pCountA + pCountB || 1;
    return {
      possessionA: Math.round((pCountA / totalPossession) * 100),
      possessionB: Math.round((pCountB / totalPossession) * 100),
      passesA: passA,
      passesB: passB,
      passesSuccessA: passSuccessA,
      passesSuccessB: passSuccessB,
      shotsA: shotA,
      shotsB: shotB,
      sprintsA: sprintA,
      sprintsB: sprintB
    };
  }, [events]);

  // Aggregate selected player stats
  const selectedPlayerStats = useMemo(() => {
    if (!selectedPlayer) return null;
    const pid = selectedPlayer.player_id;
    const team = selectedPlayer.team_classification;

    let totalPasses = 0;
    let successPasses = 0;
    let totalSprints = 0;
    let topSpeed = 0.0;
    let sprintDistance = 0.0;
    let possessionEvents = 0;

    events.forEach(e => {
      if (e.player_initiator === pid) {
        if (e.event_type === 'pass') {
          totalPasses++;
          if (e.details?.success === true) successPasses++;
        } else if (e.event_type === 'sprint') {
          totalSprints++;
          if (e.details?.top_speed_ms > topSpeed) topSpeed = e.details.top_speed_ms;
          if (e.details?.distance_meters) sprintDistance += e.details.distance_meters;
        } else if (e.event_type === 'possession') {
          possessionEvents++;
        }
      }
    });

    return {
      playerId: pid,
      team,
      totalPasses,
      successPasses,
      passAccuracy: totalPasses > 0 ? Math.round((successPasses / totalPasses) * 100) : 0,
      totalSprints,
      topSpeed: (topSpeed * 3.6).toFixed(1), // convert m/s to km/h
      sprintDistance: sprintDistance.toFixed(1),
      possessionSecs: (possessionEvents * 0.5).toFixed(1) // approximate hold duration
    };
  }, [selectedPlayer, events]);

  // Filtered timeline events
  const filteredEvents = useMemo(() => {
    if (eventFilter === 'all') return events;
    return events.filter(e => e.event_type === eventFilter);
  }, [events, eventFilter]);

  if (loading) {
    return (
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh' }}>
        <div style={{ textAlign: 'center' }}>
          <Loader2 className="animate-spin glow-text-cyan" size={48} color="#06B6D4" style={{ margin: '0 auto 1rem' }} />
          <h2 style={{ fontSize: '1.25rem' }}>Loading Match Telemetry...</h2>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>Downloading frame buffers and coordinates</p>
        </div>
      </div>
    );
  }

  if (error || !match) {
    return (
      <div className="container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '80vh' }}>
        <div className="glass-container" style={{ padding: '3rem', maxWidth: '500px', textAlign: 'center' }}>
          <ShieldAlert size={48} color="#F43F5E" style={{ margin: '0 auto 1.5rem' }} />
          <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>Analysis Error</h2>
          <p style={{ color: 'var(--color-text-muted)', marginBottom: '2rem' }}>{error || 'The match coordinate records could not be retrieved.'}</p>
          <Link to="/dashboard" className="btn btn-secondary">
            <ArrowLeft size={16} /> Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header className="navbar" style={{ padding: '1rem 2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Link to="/dashboard" style={{ display: 'flex', alignItems: 'center', color: 'var(--color-text-muted)' }}>
            <ArrowLeft size={20} />
          </Link>
          <div>
            <h2 style={{ fontSize: '1.25rem', margin: 0, fontWeight: 700 }}>{match.title}</h2>
            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.15rem' }}>
              <span>Frames: {match.total_frames}</span>
              <span>•</span>
              <span>Estimated: {(match.total_frames / fps).toFixed(0)} seconds</span>
            </div>
          </div>
        </div>
        <div className="nav-actions" style={{ gap: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border-color)', padding: '0.25rem 0.5rem', borderRadius: '4px' }}>
            {loadingChunk ? 'Syncing Coordinates...' : 'Telemetry Offline Buffer Cached'}
          </div>
        </div>
      </header>

      <main className="container" style={{ 
        display: 'grid', 
        gridTemplateColumns: 'minmax(0, 1fr) 380px', 
        gap: '1.5rem', 
        padding: '1.5rem',
        maxWidth: '100%',
        alignItems: 'start'
      }}>
        {/* Left: Pitch Viewport */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <PitchCanvas 
            players={mappedPlayers}
            ball={frameBall}
            onPlayerHover={(p) => {}}
            onPlayerSelect={handlePlayerSelectFromCanvas}
            selectedPlayerId={selectedPlayer?.player_id}
            showLabels={showLabels}
          />

          {/* Controls Card */}
          <div className="glass-container" style={{ padding: '1.25rem' }}>
            {/* Scrub Bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
              <span style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--color-text-muted)', width: '40px' }}>
                {formatTime(currentFrame)}
              </span>
              <input
                type="range"
                min="0"
                max={match.total_frames}
                value={currentFrame}
                onChange={handleScrubChange}
                style={{
                  flex: 1,
                  height: '4px',
                  background: 'rgba(51, 65, 85, 0.6)',
                  borderRadius: '2px',
                  outline: 'none',
                  cursor: 'pointer',
                  accentColor: 'var(--color-secondary)',
                }}
              />
              <span style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--color-text-muted)', width: '40px', textAlign: 'right' }}>
                {formatTime(match.total_frames)}
              </span>
            </div>

            {/* Operations buttons */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button 
                  onClick={handlePlayPause} 
                  className="btn btn-secondary" 
                  style={{ 
                    width: '3rem', 
                    height: '3rem', 
                    borderRadius: '50%', 
                    padding: 0,
                    boxShadow: '0 0 15px rgba(6, 182, 212, 0.4)' 
                  }}
                >
                  {isPlaying ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" style={{ marginLeft: '2px' }} />}
                </button>

                <div style={{ display: 'flex', background: 'rgba(15, 23, 42, 0.5)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '2px' }}>
                  {[0.25, 0.5, 1, 2, 4].map((s) => (
                    <button
                      key={s}
                      onClick={() => setSpeed(s)}
                      style={{
                        background: speed === s ? 'var(--color-secondary)' : 'transparent',
                        color: speed === s ? '#FFFFFF' : 'var(--color-text-muted)',
                        border: 'none',
                        padding: '0.35rem 0.6rem',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        borderRadius: '6px',
                        cursor: 'pointer',
                        transition: 'var(--transition)'
                      }}
                    >
                      {s}x
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-muted)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={showLabels}
                    onChange={(e) => setShowLabels(e.target.checked)}
                    style={{ accentColor: 'var(--color-primary)' }}
                  />
                  Show Squad ID Labels
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Sidebar Analytics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: '100%' }}>
          {/* Tabs header */}
          <div className="glass-container" style={{ padding: '0.25rem', display: 'flex' }}>
            {[
              { id: 'timeline', label: 'Timeline' },
              { id: 'stats', label: 'Match Stats' },
              { id: 'player', label: 'Player Analyst' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  flex: 1,
                  background: activeTab === tab.id ? 'rgba(30, 41, 59, 0.8)' : 'transparent',
                  color: activeTab === tab.id ? '#FFFFFF' : 'var(--color-text-muted)',
                  border: 'none',
                  borderBottom: activeTab === tab.id ? '2px solid var(--color-secondary)' : 'none',
                  padding: '0.75rem 0.25rem',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  cursor: 'pointer',
                  borderRadius: '6px',
                  transition: 'var(--transition)'
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content area */}
          <div className="glass-container" style={{ padding: '1.5rem', minHeight: '450px', maxHeight: '580px', overflowY: 'auto', textAlign: 'left', display: 'flex', flexDirection: 'column' }}>
            
            {/* Timeline Tab */}
            {activeTab === 'timeline' && (
              <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                {/* Event Filters */}
                <div style={{ display: 'flex', gap: '0.35rem', overflowX: 'auto', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-color)', marginBottom: '1rem' }}>
                  {[
                    { id: 'all', label: 'All' },
                    { id: 'pass', label: 'Passes' },
                    { id: 'shot', label: 'Shots' },
                    { id: 'sprint', label: 'Sprints' },
                    { id: 'interception', label: 'Intercepts' }
                  ].map((filter) => (
                    <button
                      key={filter.id}
                      onClick={() => setEventFilter(filter.id)}
                      style={{
                        background: eventFilter === filter.id ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
                        color: eventFilter === filter.id ? 'var(--color-secondary)' : 'var(--color-text-muted)',
                        border: '1px solid',
                        borderColor: eventFilter === filter.id ? 'rgba(6, 182, 212, 0.3)' : 'var(--border-color)',
                        padding: '0.25rem 0.6rem',
                        fontSize: '0.75rem',
                        borderRadius: '9999px',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>

                {/* Timeline feed */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto', flex: 1 }}>
                  {filteredEvents.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--color-text-muted)' }}>
                      <Tv size={32} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                      <p style={{ fontSize: '0.85rem' }}>No events recorded for this category.</p>
                    </div>
                  ) : (
                    filteredEvents.map((e) => {
                      // Format descriptions nicely
                      let title = '';
                      let desc = '';
                      let iconColor = '#9CA3AF';
                      if (e.event_type === 'possession') {
                        title = 'Possession shift';
                        desc = `${e.team === 'team_a' ? 'Team A' : 'Team B'} #${e.player_initiator} took control`;
                        iconColor = e.team === 'team_a' ? 'var(--team-a)' : 'var(--team-b)';
                      } else if (e.event_type === 'pass') {
                        const isSuccess = e.details?.success === true;
                        title = isSuccess ? 'Pass Completed' : 'Failed Pass';
                        desc = `${e.team === 'team_a' ? 'Team A' : 'Team B'} #${e.player_initiator} ➜ #${e.player_receiver}`;
                        iconColor = isSuccess ? 'var(--color-primary)' : '#EF4444';
                      } else if (e.event_type === 'shot') {
                        title = 'Shot on Goal';
                        desc = `${e.team === 'team_a' ? 'Team A' : 'Team B'} #${e.player_initiator} shot (${e.details?.speed_ms}m/s)`;
                        iconColor = '#F59E0B';
                      } else if (e.event_type === 'sprint') {
                        title = 'Player Sprint Run';
                        desc = `${e.team === 'team_a' ? 'Team A' : 'Team B'} #${e.player_initiator} (${(e.details?.top_speed_ms * 3.6).toFixed(1)} km/h)`;
                        iconColor = 'var(--color-secondary)';
                      } else if (e.event_type === 'interception') {
                        title = 'Interception';
                        desc = `${e.team === 'team_a' ? 'Team A' : 'Team B'} intercepted pass`;
                        iconColor = '#EF4444';
                      }

                      return (
                        <div 
                          key={e.id} 
                          className="glass-card" 
                          onClick={() => handleEventClick(e)}
                          style={{ 
                            padding: '0.75rem 1rem', 
                            cursor: 'pointer',
                            display: 'flex',
                            gap: '0.75rem',
                            alignItems: 'center',
                            background: currentFrame >= e.frame_number && currentFrame < e.frame_number + 60 
                              ? 'rgba(6, 182, 212, 0.08)' 
                              : 'rgba(30, 41, 59, 0.35)',
                            borderColor: currentFrame >= e.frame_number && currentFrame < e.frame_number + 60 
                              ? 'rgba(6, 182, 212, 0.4)' 
                              : 'rgba(51, 65, 85, 0.2)'
                          }}
                        >
                          <div style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            background: iconColor,
                            boxShadow: `0 0 6px ${iconColor}`
                          }} />
                          <div style={{ flex: 1 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#FFF' }}>{title}</span>
                              <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--color-text-muted)' }}>
                                {formatTime(e.frame_number)}
                              </span>
                            </div>
                            <p style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginTop: '0.15rem' }}>{desc}</p>
                          </div>
                          <ChevronRight size={14} style={{ color: 'var(--color-text-muted)' }} />
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}

            {/* Match Stats Tab */}
            {activeTab === 'stats' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Tactical Metrics Overview</h3>
                
                {/* Possession bar */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                    <span style={{ color: 'var(--team-a)', fontWeight: 600 }}>Team A ({stats.possessionA}%)</span>
                    <span>Ball Possession</span>
                    <span style={{ color: 'var(--team-b)', fontWeight: 600 }}>Team B ({stats.possessionB}%)</span>
                  </div>
                  <div style={{ display: 'flex', height: '10px', borderRadius: '5px', overflow: 'hidden', background: '#334155' }}>
                    <div style={{ width: `${stats.possessionA}%`, background: 'var(--team-a)' }}></div>
                    <div style={{ width: `${stats.possessionB}%`, background: 'var(--team-b)' }}></div>
                  </div>
                </div>

                {/* Sprints Stats */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
                  <div style={{ background: 'rgba(15,23,42,0.4)', padding: '0.75rem', borderRadius: '8px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>TEAM A SPRINTS</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--team-a)', marginTop: '0.25rem' }}>
                      {stats.sprintsA}
                    </div>
                  </div>
                  <div style={{ background: 'rgba(15,23,42,0.4)', padding: '0.75rem', borderRadius: '8px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>TEAM B SPRINTS</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--team-b)', marginTop: '0.25rem' }}>
                      {stats.sprintsB}
                    </div>
                  </div>
                </div>

                {/* Shots & Goals */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div style={{ background: 'rgba(15,23,42,0.4)', padding: '0.75rem', borderRadius: '8px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>TEAM A SHOTS</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--team-a)', marginTop: '0.25rem' }}>
                      {stats.shotsA}
                    </div>
                  </div>
                  <div style={{ background: 'rgba(15,23,42,0.4)', padding: '0.75rem', borderRadius: '8px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>TEAM B SHOTS</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--team-b)', marginTop: '0.25rem' }}>
                      {stats.shotsB}
                    </div>
                  </div>
                </div>

                {/* Passes Counts */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', borderTop: '1px solid var(--border-color)', paddingTop: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>TEAM A PASSES COMPLETED</span>
                    <span style={{ fontWeight: 600, color: '#FFF' }}>
                      {stats.passesSuccessA} / {stats.passesA} ({stats.passesA > 0 ? Math.round((stats.passesSuccessA / stats.passesA) * 100) : 0}%)
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>TEAM B PASSES COMPLETED</span>
                    <span style={{ fontWeight: 600, color: '#FFF' }}>
                      {stats.passesSuccessB} / {stats.passesB} ({stats.passesB > 0 ? Math.round((stats.passesSuccessB / stats.passesB) * 100) : 0}%)
                    </span>
                  </div>
                </div>

              </div>
            )}

            {/* Selected Player Tab */}
            {activeTab === 'player' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {!selectedPlayerStats ? (
                  <div style={{ textAlign: 'center', padding: '4rem 0', color: 'var(--color-text-muted)' }}>
                    <User size={36} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                    <p style={{ fontSize: '0.9rem' }}>Select a player dot on the top-down pitch canvas to analyze detailed tactical telemetry.</p>
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-color)' }}>
                      <div style={{ 
                        width: '36px', 
                        height: '36px', 
                        borderRadius: '50%', 
                        background: selectedPlayerStats.team === 'team_a' ? 'var(--team-a)' : 'var(--team-b)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#FFFFFF',
                        fontWeight: 'bold',
                        fontSize: '1rem',
                        boxShadow: `0 0 10px ${selectedPlayerStats.team === 'team_a' ? 'var(--team-a)' : 'var(--team-b)'}`
                      }}>
                        {selectedPlayerStats.playerId}
                      </div>
                      <div>
                        <h4 style={{ margin: 0, fontSize: '1.1rem' }}>Squad ID #{selectedPlayerStats.playerId}</h4>
                        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          {selectedPlayerStats.team === 'team_a' ? 'Team A (Cyan)' : 'Team B (Coral)'}
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.4)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Pass Success Rate</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-primary)' }}>
                          {selectedPlayerStats.passAccuracy}% ({selectedPlayerStats.successPasses}/{selectedPlayerStats.totalPasses})
                        </span>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.4)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Total Sprint Runs</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-secondary)' }}>
                          {selectedPlayerStats.totalSprints}
                        </span>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.4)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Max Sprint Speed</span>
                        <span style={{ fontWeight: 600, color: '#FFF' }}>
                          {selectedPlayerStats.topSpeed} km/h
                        </span>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.4)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Sprint Distance Covered</span>
                        <span style={{ fontWeight: 600, color: '#FFF' }}>
                          {selectedPlayerStats.sprintDistance} meters
                        </span>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(15,23,42,0.4)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>Hold/Possession Duration</span>
                        <span style={{ fontWeight: 600, color: '#FFF' }}>
                          {selectedPlayerStats.possessionSecs} seconds
                        </span>
                      </div>
                    </div>
                    
                    <button 
                      onClick={() => setSelectedPlayer(null)} 
                      className="btn btn-outline" 
                      style={{ fontSize: '0.8rem', padding: '0.4rem', width: '100%', marginTop: '0.5rem' }}
                    >
                      Clear Selection
                    </button>
                  </>
                )}
              </div>
            )}

          </div>
        </div>
      </main>
    </div>
  );
}
