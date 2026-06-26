import React, { useRef, useEffect, useState } from 'react';

export default function PitchCanvas({ 
  players = [], 
  ball = null, 
  onPlayerHover = null, 
  onPlayerSelect = null,
  selectedPlayerId = null,
  showLabels = true
}) {
  const canvasRef = useRef(null);
  const [hoveredPlayer, setHoveredPlayer] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  // Constants for pitch dimension mapping (Scale: 10 pixels per meter)
  const PITCH_WIDTH = 1050; // 105m
  const PITCH_HEIGHT = 680; // 68m
  const SCALE = 10; 

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear Canvas
    ctx.clearRect(0, 0, PITCH_WIDTH, PITCH_HEIGHT);

    // --- DRAW PITCH BACKGROUND & GRASS ---
    // Premium dark space-slate/green turf
    ctx.fillStyle = '#0F172A'; // Deep Slate background
    ctx.fillRect(0, 0, PITCH_WIDTH, PITCH_HEIGHT);
    
    // Draw subtle grass strips
    const stripWidth = PITCH_WIDTH / 15;
    for (let i = 0; i < 15; i++) {
      ctx.fillStyle = i % 2 === 0 ? 'rgba(16, 185, 129, 0.05)' : 'rgba(16, 185, 129, 0.03)';
      ctx.fillRect(i * stripWidth, 0, stripWidth, PITCH_HEIGHT);
    }

    // --- DRAW MARKINGS ---
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.65)';
    ctx.lineWidth = 2;
    ctx.shadowBlur = 0;

    // Pitch Boundary Line
    ctx.strokeRect(0, 0, PITCH_WIDTH, PITCH_HEIGHT);

    // Halfway Line
    ctx.beginPath();
    ctx.moveTo(PITCH_WIDTH / 2, 0);
    ctx.lineTo(PITCH_WIDTH / 2, PITCH_HEIGHT);
    ctx.stroke();

    // Center Circle (Radius: 9.15m -> 91.5px)
    ctx.beginPath();
    ctx.arc(PITCH_WIDTH / 2, PITCH_HEIGHT / 2, 9.15 * SCALE, 0, 2 * Math.PI);
    ctx.stroke();

    // Center Spot
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.beginPath();
    ctx.arc(PITCH_WIDTH / 2, PITCH_HEIGHT / 2, 4, 0, 2 * Math.PI);
    ctx.fill();

    // -- Left Penalty Area --
    // Outer Box (16.5m deep, 40.3m wide, centered on Y=340px)
    // 16.5m -> 165px. Width of box -> 403px. Y starts at (340 - 201.5) = 138.5px
    ctx.strokeRect(0, 13.85 * SCALE, 16.5 * SCALE, 40.3 * SCALE);

    // Inner Goal Area (5.5m deep, 18.32m wide)
    // 5.5m -> 55px. Width of box -> 183.2px. Y starts at (340 - 91.6) = 248.4px
    ctx.strokeRect(0, 24.84 * SCALE, 5.5 * SCALE, 18.32 * SCALE);

    // Left Penalty Spot (11m -> 110px from goal line)
    ctx.beginPath();
    ctx.arc(11 * SCALE, PITCH_HEIGHT / 2, 3, 0, 2 * Math.PI);
    ctx.fill();

    // Left Penalty Arc (Radius 9.15m from Spot, only X > 16.5m)
    ctx.beginPath();
    ctx.arc(11 * SCALE, PITCH_HEIGHT / 2, 9.15 * SCALE, -Math.acos(5.5 / 9.15), Math.acos(5.5 / 9.15));
    ctx.stroke();

    // -- Right Penalty Area --
    // Outer Box
    ctx.strokeRect(PITCH_WIDTH - (16.5 * SCALE), 13.85 * SCALE, 16.5 * SCALE, 40.3 * SCALE);

    // Inner Goal Area
    ctx.strokeRect(PITCH_WIDTH - (5.5 * SCALE), 24.84 * SCALE, 5.5 * SCALE, 18.32 * SCALE);

    // Right Penalty Spot
    ctx.beginPath();
    ctx.arc(PITCH_WIDTH - (11 * SCALE), PITCH_HEIGHT / 2, 3, 0, 2 * Math.PI);
    ctx.fill();

    // Right Penalty Arc
    ctx.beginPath();
    ctx.arc(PITCH_WIDTH - (11 * SCALE), PITCH_HEIGHT / 2, 9.15 * SCALE, Math.PI - Math.acos(5.5 / 9.15), Math.PI + Math.acos(5.5 / 9.15));
    ctx.stroke();

    // Goals (behind the goal lines)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    // Left Goal (depth 2m)
    ctx.strokeRect(-2 * SCALE, 30.34 * SCALE, 2 * SCALE, 7.32 * SCALE);
    // Right Goal (depth 2m)
    ctx.strokeRect(PITCH_WIDTH, 30.34 * SCALE, 2 * SCALE, 7.32 * SCALE);

    // --- DRAW PLAYERS ---
    players.forEach((player) => {
      const px = player.x_coord * SCALE;
      const py = player.y_coord * SCALE;
      const isSelected = selectedPlayerId === player.player_id;
      const isHovered = hoveredPlayer && hoveredPlayer.player_id === player.player_id;

      // Color coding based on team
      let color = '#718096'; // gray default
      let shadowColor = 'rgba(113, 128, 150, 0.3)';
      if (player.team_classification === 'team_a') {
        color = '#0EA5E9'; // Cyber Blue
        shadowColor = 'rgba(14, 165, 233, 0.5)';
      } else if (player.team_classification === 'team_b') {
        color = '#F43F5E'; // Hot Coral
        shadowColor = 'rgba(244, 63, 94, 0.5)';
      } else if (player.team_classification === 'referee') {
        color = '#F59E0B'; // Golden Yellow
        shadowColor = 'rgba(245, 158, 11, 0.5)';
      }

      // Outer Selection/Hover Glowing Ring
      if (isSelected || isHovered) {
        ctx.shadowBlur = 10;
        ctx.shadowColor = isSelected ? '#10B981' : '#06B6D4';
        ctx.strokeStyle = isSelected ? '#10B981' : '#06B6D4';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(px, py, 11, 0, 2 * Math.PI);
        ctx.stroke();
        
        ctx.shadowBlur = 0; // reset
        ctx.lineWidth = 2; // reset
      }

      // Base player circle shadow
      ctx.shadowBlur = 6;
      ctx.shadowColor = shadowColor;
      ctx.fillStyle = color;

      ctx.beginPath();
      ctx.arc(px, py, 7.5, 0, 2 * Math.PI);
      ctx.fill();
      
      // Draw subtle white border
      ctx.shadowBlur = 0; // reset
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Inside text (numbers/IDs)
      if (showLabels && player.team_classification !== 'referee') {
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(player.player_id.toString(), px, py + 0.5);
      }
    });

    // --- DRAW BALL ---
    if (ball) {
      const bx = ball.x_coord * SCALE;
      const by = ball.y_coord * SCALE;

      // Draw Ball Glow
      ctx.shadowBlur = 12;
      ctx.shadowColor = '#39FF14'; // Neon Green glow
      
      // Ball Outer Neon circle
      ctx.fillStyle = '#39FF14';
      ctx.beginPath();
      ctx.arc(bx, by, 5, 0, 2 * Math.PI);
      ctx.fill();

      // Ball Inner White core
      ctx.shadowBlur = 0;
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.arc(bx, by, 2.5, 0, 2 * Math.PI);
      ctx.fill();
    }

    // --- DRAW TOOLTIP ON HOVER ---
    if (hoveredPlayer) {
      const hx = hoveredPlayer.x_coord * SCALE;
      const hy = hoveredPlayer.y_coord * SCALE;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.8)';
      ctx.lineWidth = 1;
      
      const tooltipText = `Player #${hoveredPlayer.player_id} (${hoveredPlayer.team_classification === 'team_a' ? 'Team A' : hoveredPlayer.team_classification === 'team_b' ? 'Team B' : 'Referee'})`;
      ctx.font = '500 12px var(--font-sans), sans-serif';
      const textWidth = ctx.measureText(tooltipText).width;
      
      const rectWidth = textWidth + 16;
      const rectHeight = 28;
      
      // Keep tooltip within bounds
      let rectX = hx - rectWidth / 2;
      let rectY = hy - 38;
      if (rectX < 4) rectX = 4;
      if (rectX + rectWidth > PITCH_WIDTH - 4) rectX = PITCH_WIDTH - rectWidth - 4;
      if (rectY < 4) rectY = hy + 18;

      // Draw Tooltip Container
      ctx.beginPath();
      ctx.roundRect(rectX, rectY, rectWidth, rectHeight, 6);
      ctx.fill();
      ctx.stroke();

      // Draw Text
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(tooltipText, rectX + rectWidth / 2, rectY + rectHeight / 2);
    }

  }, [players, ball, hoveredPlayer, selectedPlayerId, showLabels]);

  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    
    // Scale client mouse coordinates back to canvas logical coordinates
    const scaleX = PITCH_WIDTH / rect.width;
    const scaleY = PITCH_HEIGHT / rect.height;

    const mouseX = (e.clientX - rect.left) * scaleX;
    const mouseY = (e.clientY - rect.top) * scaleY;

    setMousePos({ x: mouseX, y: mouseY });

    // Check hit test for players
    // Player radius is 7.5px, hit boundary is 12px (1.2m)
    const HIT_RADIUS = 15;
    let found = null;

    for (const player of players) {
      const px = player.x_coord * SCALE;
      const py = player.y_coord * SCALE;
      const dist = Math.hypot(mouseX - px, mouseY - py);
      if (dist < HIT_RADIUS) {
        found = player;
        break; // Stop at first match
      }
    }

    if (found !== hoveredPlayer) {
      setHoveredPlayer(found);
      if (onPlayerHover) {
        onPlayerHover(found);
      }
    }
  };

  const handleMouseLeave = () => {
    setHoveredPlayer(null);
    if (onPlayerHover) {
      onPlayerHover(null);
    }
  };

  const handleCanvasClick = () => {
    if (hoveredPlayer) {
      if (onPlayerSelect) {
        onPlayerSelect(hoveredPlayer);
      }
    } else {
      if (onPlayerSelect) {
        onPlayerSelect(null); // Deselect
      }
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: '12px', border: '1px solid var(--border-color)', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
      <canvas
        ref={canvasRef}
        width={PITCH_WIDTH}
        height={PITCH_HEIGHT}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleCanvasClick}
        style={{
          display: 'block',
          width: '100%',
          height: 'auto',
          aspectRatio: `${PITCH_WIDTH} / ${PITCH_HEIGHT}`,
          cursor: hoveredPlayer ? 'pointer' : 'default',
        }}
      />
    </div>
  );
}
