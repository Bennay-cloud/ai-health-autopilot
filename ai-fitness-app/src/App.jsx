import React, { useState, useEffect } from 'react';
import DOMPurify from 'dompurify';
import './index.css';

const API = 'http://127.0.0.1:8000';

const STEPS = [
  { label: 'Profil' },
  { label: 'Ziele' },
  { label: 'Training & Heute' },
];

const DAY_LABELS  = { recovery: 'Recovery', performance: 'Performance', normal: 'Normal' };
const DAY_COLORS  = { recovery: 'recovery', performance: 'performance', normal: 'normal' };

const CYCLE_PHASE_LABELS = {
  menstruation: 'Menstruation',
  follicular:   'Follikelphase',
  ovulation:    'Eisprung',
  luteal:       'Lutealphase',
};

const CYCLE_PHASE_EXPLANATIONS = {
  menstruation: 'Niedrigere Intensität empfohlen. Fokus auf Mobilität, Spazierengehen, Yoga oder leichtes Krafttraining.',
  follicular:   'Energie steigt. Krafttraining und höhere Intensität sind gut geeignet.',
  ovulation:    'Performance-Fenster. Höhere Intensität kann optimal genutzt werden.',
  luteal:       'Erholungsunterstützung wichtig. Vermeide sehr hohe Intensität bei hohem Stress oder wenig Schlaf.',
};

const SCHEDULE_ICON = {
  meal:     '🌅',
  delivery: '🚚',
  workout:  '🏋️',
  recovery: '💤',
};

const GENDER_LABEL         = { male: 'Männlich', female: 'Weiblich', other: 'Divers' };
const GENDER_TO_GESCHLECHT = { male: 'Mann', female: 'Frau', other: 'Divers' };

const CALENDAR_PRESETS = [
  {
    id: 'entspannt',
    label: '🟢 Entspannter Tag',
    events: [
      { title: 'Kurzes Check-in', start_time: '09:00', end_time: '09:30' },
    ],
  },
  {
    id: 'meetings',
    label: '🟡 Viele Meetings',
    events: [
      { title: 'Standup',         start_time: '09:00', end_time: '09:30' },
      { title: 'Sprint Planning', start_time: '10:00', end_time: '11:30' },
      { title: 'Business Lunch',  start_time: '12:00', end_time: '13:30' },
      { title: 'Client Call',     start_time: '14:00', end_time: '15:30' },
      { title: 'Retrospektive',   start_time: '16:00', end_time: '17:00' },
    ],
  },
  {
    id: 'vollerKalender',
    label: '🔴 Voller Kalender',
    events: [
      { title: 'Strategie-Workshop', start_time: '08:00', end_time: '12:00' },
      { title: 'Mittagessen',        start_time: '12:00', end_time: '13:00' },
      { title: 'Präsentation',       start_time: '13:00', end_time: '17:00' },
      { title: 'Nachbesprechung',    start_time: '17:00', end_time: '18:30' },
    ],
  },
  {
    id: 'reisetag',
    label: '✈️ Reisetag',
    events: [
      { title: 'Reise / Flug',  start_time: '06:00', end_time: '12:00' },
      { title: 'Kundentermin',  start_time: '14:00', end_time: '18:00' },
    ],
  },
];

// ── Helper ────────────────────────────────────────────────────────

/**
 * Detect timed exercises (planks, holds, etc.) from reps_or_duration strings.
 * Returns duration in seconds, or null for rep-based exercises.
 */
function parseTimerSecs(repsOrDuration) {
  if (!repsOrDuration) return null;
  const s = repsOrDuration.toLowerCase();
  const secMatch = s.match(/(\d+)\s*sec/);
  if (secMatch) return parseInt(secMatch[1], 10);
  const minMatch = s.match(/(\d+)\s*min/);
  if (minMatch) return parseInt(minMatch[1], 10) * 60;
  return null;
}

function fmtTime(secs) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const MOTIVATIONAL_MESSAGES = [
  'Exzellent! Du hast heute alles gegeben.',
  'Stark. Jede Einheit bringt dich näher an dein Ziel.',
  'Gut gemacht! Konsistenz ist der Schlüssel.',
  'Das war stark! Dein Körper dankt es dir.',
  'Klasse! Dein Durchhaltevermögen ist beeindruckend.',
];

function scoreColor(score) {
  if (score >= 70) return 'score-high';
  if (score >= 40) return 'score-mid';
  return 'score-low';
}

function calcDayLoad(events) {
  if (events.length === 0) return 'low';
  const totalMins = events.reduce((sum, ev) => {
    const [sh, sm] = ev.start_time.split(':').map(Number);
    const [eh, em] = ev.end_time.split(':').map(Number);
    return sum + Math.max(0, eh * 60 + em - (sh * 60 + sm));
  }, 0);
  if (totalMins >= 360) return 'high';
  if (totalMins >= 120) return 'medium';
  return 'low';
}

function calcAIAdjustments(events) {
  if (events.length === 0) return null;
  const load = calcDayLoad(events);
  const hasTravel = events.some(ev =>
    ev.title.toLowerCase().includes('reis') || ev.title.toLowerCase().includes('flug')
  );
  const lunchBlocked = events.some(ev => {
    const [sh] = ev.start_time.split(':').map(Number);
    const [eh] = ev.end_time.split(':').map(Number);
    return sh <= 12 && eh >= 13;
  });
  if (hasTravel) return {
    scenario: 'Reisetag erkannt',
    adjustments: [
      'Workout auf 20 Min Bodyweight-Training angepasst',
      'Mahlzeiten auf unterwegs-freundliche Optionen umgestellt',
      'Fokus auf leichte Energie und Hydration',
    ],
    workoutAfter: '20 min', lunchAfter: '13:00',
  };
  if (load === 'high') return {
    scenario: 'Voller Kalender erkannt',
    adjustments: [
      'Workout auf Regeneration reduziert (20 Min)',
      lunchBlocked ? 'Lunch-Lieferung auf 11:30 vorgezogen' : 'Mahlzeiten auf schnelle Optionen optimiert',
      'Fokus auf mentale Erholung und Schlafqualität',
    ],
    workoutAfter: '20 min', lunchAfter: lunchBlocked ? '11:30' : '12:30',
  };
  if (load === 'medium') return {
    scenario: 'Mehrere Meetings erkannt',
    adjustments: [
      'Workout von 55 auf 30 Minuten verkürzt',
      lunchBlocked ? 'Lunch-Lieferung auf 11:30 vorgezogen' : 'Lunch-Lieferung auf 12:00 angepasst',
      'Fokus auf Energie und Konzentration',
    ],
    workoutAfter: '30 min', lunchAfter: lunchBlocked ? '11:30' : '12:00',
  };
  return {
    scenario: 'Entspannter Tag – keine Einschränkungen',
    adjustments: [
      'Volles Workout möglich (55 Min)',
      'Standard-Lieferzeiten beibehalten',
      'Fokus auf Performance und Kraft',
    ],
    workoutAfter: '55 min', lunchAfter: '12:30',
  };
}


// ── Occupational Health Constants ─────────────────────────────────

const PROFESSION_OPTIONS = [
  { id: 'chef',                 label: 'Chef' },
  { id: 'construction_worker',  label: 'Construction Worker' },
  { id: 'driver',               label: 'Driver' },
  { id: 'freelancer',           label: 'Freelancer' },
  { id: 'manager',              label: 'Manager' },
  { id: 'nurse',                label: 'Nurse' },
  { id: 'office_worker',        label: 'Office Worker' },
  { id: 'physiotherapist',      label: 'Physiotherapist' },
  { id: 'sales_representative', label: 'Sales Representative' },
  { id: 'software_engineer',    label: 'Software Engineer' },
  { id: 'student',              label: 'Student' },
  { id: 'teacher',              label: 'Teacher' },
];

const PAIN_AREA_OPTIONS = [
  { id: 'neck',       label: 'Neck' },
  { id: 'shoulder',   label: 'Shoulder' },
  { id: 'upper_back', label: 'Upper Back' },
  { id: 'lower_back', label: 'Lower Back' },
  { id: 'wrist',      label: 'Wrist' },
  { id: 'hip',        label: 'Hip' },
  { id: 'knee',       label: 'Knee' },
  { id: 'ankle',      label: 'Ankle' },
];

const URGENCY_CONFIG = {
  high:       { label: 'High Priority',   cls: 'urgency-high' },
  medium:     { label: 'Medium Priority', cls: 'urgency-medium' },
  supporting: { label: 'Supporting',      cls: 'urgency-supporting' },
};

// ── PainAreaSelector ──────────────────────────────────────────────

function PainAreaSelector({ selectedAreas, onChange }) {
  const isSelected = (id) => selectedAreas.some(a => a.area === id);
  const getSeverity = (id) => selectedAreas.find(a => a.area === id)?.severity || 5;

  const toggle = (id) => {
    if (isSelected(id)) {
      onChange(selectedAreas.filter(a => a.area !== id));
    } else {
      onChange([...selectedAreas, { area: id, severity: 5 }]);
    }
  };

  const setSeverity = (id, severity) => {
    onChange(selectedAreas.map(a => a.area === id ? { ...a, severity: parseInt(severity) } : a));
  };

  function severityLabel(v) {
    if (v <= 3) return 'Mild';
    if (v <= 6) return 'Moderate';
    return 'Severe';
  }

  return (
    <div className="pain-selector">
      <div className="pain-chips">
        {PAIN_AREA_OPTIONS.map(opt => (
          <button
            key={opt.id}
            type="button"
            className={`pain-chip ${isSelected(opt.id) ? 'pain-chip-active' : ''}`}
            onClick={() => toggle(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {selectedAreas.length > 0 && (
        <div className="pain-severity-list">
          {selectedAreas.map(a => {
            const opt = PAIN_AREA_OPTIONS.find(o => o.id === a.area);
            return (
              <div key={a.area} className="pain-severity-row">
                <span className="pain-severity-label">{opt?.label}</span>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={a.severity}
                  onChange={e => setSeverity(a.area, e.target.value)}
                  className="pain-severity-slider"
                />
                <span className={`pain-severity-value sev-${a.severity >= 7 ? 'high' : a.severity >= 4 ? 'mid' : 'low'}`}>
                  {a.severity}/10 · {severityLabel(a.severity)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── HealthAdvisorPanel ────────────────────────────────────────────

function HealthAdvisorPanel({ message, profession }) {
  if (!message) return null;
  return (
    <div className="health-advisor-panel">
      <div className="hap-header">
        <span className="hap-icon">⚕</span>
        <div>
          <div className="hap-title">AI Health Advisor</div>
          {profession && <div className="hap-sub">{profession}</div>}
        </div>
      </div>
      <p className="hap-message">{message}</p>
    </div>
  );
}

// ── OccupationalRiskCard ──────────────────────────────────────────

function OccupationalRiskCard({ occProfile, painAreas }) {
  if (!occProfile) return null;
  return (
    <div className="occ-risk-card">
      <div className="orc-header">
        <span className="orc-icon">🏢</span>
        <div>
          <div className="orc-title">Your Work Profile</div>
          <div className="orc-profession">{occProfile.profession_display}</div>
        </div>
      </div>

      <div className="orc-demands">
        <div className="orc-section-label">Work Demands</div>
        <div className="orc-demands-list">
          {occProfile.work_demands.slice(0, 3).map((d, i) => (
            <span key={i} className="orc-demand-chip">{d}</span>
          ))}
        </div>
      </div>

      <div className="orc-risks">
        <div className="orc-section-label">Health Risks Detected</div>
        {occProfile.health_risks.slice(0, 4).map((r, i) => (
          <div key={i} className="orc-risk-item">
            <span className="orc-risk-dot" />
            <span>{r}</span>
          </div>
        ))}
      </div>

      {painAreas && painAreas.length > 0 && (
        <div className="orc-pain-areas">
          <div className="orc-section-label">Reported Pain Areas</div>
          <div className="orc-pain-chips">
            {painAreas.map((p, i) => (
              <span
                key={i}
                className={`orc-pain-chip sev-chip-${p.severity >= 7 ? 'high' : p.severity >= 4 ? 'mid' : 'low'}`}
              >
                {p.area.replace('_', ' ')} · {p.severity}/10
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── HealthPriorityStack ───────────────────────────────────────────

function HealthPriorityStack({ priorities }) {
  if (!priorities || priorities.length === 0) return null;
  return (
    <div className="health-priority-stack">
      <div className="hps-header">
        <span className="hps-icon">🎯</span>
        <div className="hps-title">Your Health Priorities</div>
      </div>
      <div className="hps-list">
        {priorities.map((p, i) => {
          const uc = URGENCY_CONFIG[p.urgency] || URGENCY_CONFIG.supporting;
          return (
            <div key={i} className={`hps-item ${uc.cls}`}>
              <div className="hps-rank">#{p.rank}</div>
              <div className="hps-content">
                <div className="hps-label">{p.human_label}</div>
                <div className="hps-reason">{p.reason}</div>
              </div>
              <span className={`hps-urgency-badge ${uc.cls}`}>{uc.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── WhyThisMattersCard ────────────────────────────────────────────

function WhyThisMattersCard({ data }) {
  const [openSection, setOpenSection] = useState(null);
  if (!data) return null;

  const toggle = (key) => setOpenSection(s => s === key ? null : key);

  const sections = [
    {
      key: 'work_profile',
      icon: '🏢',
      title: 'Your Work Profile',
      content: <p className="wtm-text">{data.work_profile_summary}</p>,
    },
    {
      key: 'risks',
      icon: '⚠',
      title: 'Health Risks Detected',
      content: (
        <ul className="wtm-list">
          {data.risks_detected.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      ),
    },
    {
      key: 'priority',
      icon: '🎯',
      title: "Today's Priority",
      content: (
        <>
          <div className="wtm-priority-label">{data.todays_priority}</div>
          <p className="wtm-text">{data.todays_priority_reason}</p>
        </>
      ),
    },
    {
      key: 'body',
      icon: '🔬',
      title: 'What Happens Inside Your Body',
      content: (
        <ul className="wtm-list">
          {data.physiological_adaptations.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      ),
    },
    {
      key: 'work',
      icon: '💼',
      title: 'How This Helps You At Work',
      content: (
        <>
          <div className="wtm-work-profession">{data.work_performance_benefits.profession_display}</div>
          <ul className="wtm-list wtm-work-list">
            {data.work_performance_benefits.benefits.map((b, i) => (
              <li key={i} className="wtm-work-benefit">
                <span className="wtm-check">✓</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        </>
      ),
    },
    {
      key: 'longterm',
      icon: '📈',
      title: 'Long-Term Health Impact',
      content: (
        <ul className="wtm-list">
          {data.long_term_benefits.map((b, i) => <li key={i}>{b}</li>)}
        </ul>
      ),
    },
    {
      key: 'ignored',
      icon: '❗',
      title: 'What Happens If This Is Ignored?',
      content: (
        <>
          {data.what_if_ignored.short_term.length > 0 && (
            <>
              <div className="wtm-ignored-sub">In the Short Term</div>
              <ul className="wtm-list wtm-ignored-list">
                {data.what_if_ignored.short_term.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </>
          )}
          {data.what_if_ignored.long_term.length > 0 && (
            <>
              <div className="wtm-ignored-sub">Over the Long Term</div>
              <ul className="wtm-list wtm-ignored-list">
                {data.what_if_ignored.long_term.map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </>
          )}
          <p className="wtm-educational-note">{data.what_if_ignored.educational_note}</p>
        </>
      ),
    },
  ];

  return (
    <div className="why-this-matters-card">
      <div className="wtm-header">
        <span className="wtm-header-icon">💡</span>
        <div className="wtm-header-title">Why This Training Matters</div>
        <div className="wtm-header-sub">Your personalised health intervention explained</div>
      </div>
      <div className="wtm-sections">
        {sections.map(sec => (
          <div key={sec.key} className={`wtm-section ${openSection === sec.key ? 'wtm-open' : ''}`}>
            <button className="wtm-section-toggle" onClick={() => toggle(sec.key)}>
              <span className="wtm-sec-icon">{sec.icon}</span>
              <span className="wtm-sec-title">{sec.title}</span>
              <span className="wtm-chevron">{openSection === sec.key ? '▲' : '▼'}</span>
            </button>
            {openSection === sec.key && (
              <div className="wtm-section-body">{sec.content}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────

function ScoreDriversCard({ drivers }) {
  if (!drivers) return null;
  return (
    <div className="drivers-card">
      <div className="drivers-title">Warum diese Entscheidung?</div>
      <div className="drivers-grid">
        <div className="drivers-col">
          <div className="drivers-col-head positive-head">Positive Faktoren</div>
          {drivers.positive.length === 0
            ? <div className="driver-empty">–</div>
            : drivers.positive.map((f, i) => (
                <div key={i} className="driver-item driver-positive">
                  <span className="driver-icon">✓</span>
                  <span>{f}</span>
                </div>
              ))}
        </div>
        <div className="drivers-col">
          <div className="drivers-col-head negative-head">Negative Faktoren</div>
          {drivers.negative.length === 0
            ? <div className="driver-empty">–</div>
            : drivers.negative.map((f, i) => (
                <div key={i} className="driver-item driver-negative">
                  <span className="driver-icon">✕</span>
                  <span>{f}</span>
                </div>
              ))}
        </div>
      </div>
    </div>
  );
}

function CyclePhasePanel({ phase }) {
  const explanation = CYCLE_PHASE_EXPLANATIONS[phase];
  if (!explanation) return null;
  return (
    <div className={`cycle-info-panel cycle-panel-${phase}`}>
      <div className="cycle-info-header">
        <span className={`cycle-phase-badge ${phase}`}>{CYCLE_PHASE_LABELS[phase]}</span>
        <span className="cycle-info-sub">Zyklus-Einfluss auf dein Training</span>
      </div>
      <p className="cycle-info-text">{explanation}</p>
    </div>
  );
}

function ScheduleTimeline({ schedule }) {
  if (!schedule || schedule.length === 0) return null;
  return (
    <div className="timeline-card">
      <div className="timeline-card-title">Heutiger Tagesplan</div>
      <div className="timeline">
        {schedule.map((item, i) => (
          <div key={i} className={`timeline-item tl-${item.type}`}>
            <div className="timeline-left">
              <div className={`timeline-dot dot-${item.type}`} />
              {i < schedule.length - 1 && <div className="timeline-line" />}
            </div>
            <div className="timeline-content">
              <span className="timeline-time">{item.time}</span>
              <span className="timeline-icon">{SCHEDULE_ICON[item.type]}</span>
              <span className="timeline-label">{item.title}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── AdherenceDashboard ────────────────────────────────────────────

function AdherenceDashboard({ data }) {
  if (!data) return null;
  const { adherence, streaks, trends, insights, at_risk, ai_insight } = data;

  function badge(pct) {
    if (pct >= 85) return { label: 'Excellent',       cls: 'adh-badge-excellent' };
    if (pct >= 70) return { label: 'Good',            cls: 'adh-badge-good' };
    if (pct >= 50) return { label: 'Needs Attention', cls: 'adh-badge-attention' };
    return           { label: 'At Risk',              cls: 'adh-badge-risk' };
  }

  function TrendArrow({ val }) {
    if (val > 5)  return <span className="trend-up">↑ +{val}%</span>;
    if (val < -5) return <span className="trend-down">↓ {val}%</span>;
    return               <span className="trend-stable">→ {val}%</span>;
  }

  function AdherenceRow({ label, pct, trend }) {
    const b  = badge(pct);
    const fill = pct >= 70 ? 'var(--success)' : pct >= 50 ? '#f59e0b' : 'var(--danger)';
    return (
      <div className="adh-row">
        <div className="adh-row-header">
          <span className="adh-label">{label}</span>
          <div className="adh-row-right">
            <span className={`adh-badge ${b.cls}`}>{b.label}</span>
            <TrendArrow val={trend} />
            <span className="adh-pct">{pct}%</span>
          </div>
        </div>
        <div className="adh-bar">
          <div className="adh-fill" style={{ width: `${Math.min(pct, 100)}%`, background: fill }} />
        </div>
      </div>
    );
  }

  const hasNonDefaultStrengths       = insights.strengths[0]        !== 'Keep going — every tracked day builds the habit';
  const hasNonDefaultRecommendations = insights.recommendations[0]  !== 'Maintain your current habits';

  return (
    <div className="weekly-plan-section">
      <div className="weekly-plan-eyebrow">Consistency &amp; Progress</div>
      <div className="card adh-dashboard">

        {/* AI insight banner */}
        {ai_insight && (
          <div className="adh-insight-banner">
            <span className="adh-insight-icon">✦</span>
            <span>{ai_insight}</span>
          </div>
        )}

        {/* AT_RISK adaptation notice */}
        {at_risk?.at_risk && (
          <div className="adh-risk-banner">
            ⚠ Plan adapted to reduce friction — keep the habit small and consistent.
          </div>
        )}

        {/* Streaks */}
        <div className="adh-streak-row">
          <div className="adh-streak-card">
            <div className="adh-streak-icon">🔥</div>
            <div className="adh-streak-value">{streaks.current_streak}</div>
            <div className="adh-streak-label">Current Streak</div>
          </div>
          <div className="adh-streak-card">
            <div className="adh-streak-icon">🏆</div>
            <div className="adh-streak-value">{streaks.best_streak}</div>
            <div className="adh-streak-label">Best Streak</div>
          </div>
        </div>

        {/* Adherence metrics */}
        {adherence.total_days_tracked > 0 ? (
          <div className="adh-metrics">
            <AdherenceRow label="Workout" pct={adherence.workout_adherence} trend={trends.workout_trend} />
            <AdherenceRow label="Meals"   pct={adherence.meal_adherence}    trend={trends.meal_trend} />
            <AdherenceRow label="Sleep"   pct={adherence.sleep_adherence}   trend={trends.sleep_trend} />
            <AdherenceRow label="Overall" pct={adherence.overall_adherence} trend={trends.overall_trend} />
          </div>
        ) : (
          <div className="adh-empty">
            Complete your first day to start tracking consistency.
          </div>
        )}

        {/* Insights */}
        {(hasNonDefaultStrengths || hasNonDefaultRecommendations) && (
          <div className="adh-insights">
            {hasNonDefaultStrengths && (
              <div className="adh-insights-col">
                <div className="adh-insights-head adh-strengths-head">Strengths</div>
                {insights.strengths.map((s, i) => (
                  <div key={i} className="adh-insight-item adh-strength">✓ {s}</div>
                ))}
              </div>
            )}
            {hasNonDefaultRecommendations && (
              <div className="adh-insights-col">
                <div className="adh-insights-head adh-recs-head">Recommendations</div>
                {insights.recommendations.map((r, i) => (
                  <div key={i} className="adh-insight-item adh-rec">→ {r}</div>
                ))}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}

// ── Outcome Tracking ──────────────────────────────────────────────

function OTToggle({ value, onChange, yesLabel = 'Yes', noLabel = 'No' }) {
  return (
    <div className="ot-toggle-group">
      <button
        className={`ot-toggle ${value === true ? 'ot-yes' : 'ot-off'}`}
        onClick={() => onChange(true)}
      >{yesLabel}</button>
      <button
        className={`ot-toggle ${value === false ? 'ot-no' : 'ot-off'}`}
        onClick={() => onChange(false)}
      >{noLabel}</button>
    </div>
  );
}

function OutcomeTracker({ recordId, recommendedDuration, onSubmitted }) {
  const [workout,       setWorkout]       = useState(null);
  const [duration,      setDuration]      = useState(recommendedDuration);
  const [mealOrdered,   setMealOrdered]   = useState(null);
  const [mealConfirmed, setMealConfirmed] = useState(null);
  const [sleep,         setSleep]         = useState(null);
  const [submitting,    setSubmitting]    = useState(false);
  const [result,        setResult]        = useState(null);
  const [error,         setError]         = useState('');

  const canSubmit = workout !== null && mealOrdered !== null && sleep !== null;

  async function handleSubmit() {
    setSubmitting(true); setError('');
    try {
      const res = await fetch(`${API}/api/decision-records/${recordId}/outcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          completed_workout:           workout,
          workout_duration_completed:  workout ? Math.max(0, parseInt(duration) || 0) : 0,
          meal_ordered:                mealOrdered,
          meal_confirmed:              mealOrdered ? (mealConfirmed ?? false) : false,
          sleep_target_achieved:       sleep,
        }),
      });
      if (!res.ok) throw new Error('server');
      const data = await res.json();
      setResult(data);
      onSubmitted?.();
    } catch {
      setError('Could not save outcomes. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  /* ── Success state ── */
  if (result?.outcome) {
    const o     = result.outcome;
    const score = o.overall_completion_percentage;
    const cls   = score >= 70 ? 'ot-score-high' : score >= 50 ? 'ot-score-mid' : 'ot-score-low';
    const mealLabel = o.meal_ordered && o.meal_confirmed ? '✓' : o.meal_ordered ? '½' : '✗';
    return (
      <div className="ot-container ot-done">
        <div className="ot-done-header">
          <span className="ot-done-check">✓</span>
          <span className="ot-done-title">Day Logged</span>
        </div>
        <div className="ot-score-row">
          <div className={`ot-score-circle ${cls}`}>
            <span className="ot-score-num">{score}%</span>
            <span className="ot-score-sub">Overall</span>
          </div>
          <div className="ot-mini-stats">
            <div className="ot-mini">
              <div className="ot-mini-val">{o.workout_completion_percentage}%</div>
              <div className="ot-mini-label">Workout</div>
            </div>
            <div className="ot-mini">
              <div className="ot-mini-val">{mealLabel}</div>
              <div className="ot-mini-label">Meals</div>
            </div>
            <div className="ot-mini">
              <div className="ot-mini-val">{o.sleep_target_achieved ? '✓' : '✗'}</div>
              <div className="ot-mini-label">Sleep</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ── Input form ── */
  return (
    <div className="ot-container">
      <div className="ot-title">Log Today's Outcomes</div>

      {/* Workout */}
      <div className="ot-section">
        <div className="ot-section-label">💪 Workout</div>
        <OTToggle
          value={workout}
          onChange={v => { setWorkout(v); setDuration(v ? recommendedDuration : 0); }}
          yesLabel="✓ Completed"
          noLabel="✗ Skipped"
        />
        {workout === true && (
          <div className="ot-duration-row">
            <label className="ot-duration-label">Minutes done</label>
            <input
              className="ot-duration-input"
              type="number" min="1" max="300"
              value={duration}
              onChange={e => setDuration(e.target.value)}
            />
            <span className="ot-duration-hint">of {recommendedDuration} recommended</span>
          </div>
        )}
      </div>

      {/* Meals */}
      <div className="ot-section">
        <div className="ot-section-label">🍽 Meals</div>
        <OTToggle
          value={mealOrdered}
          onChange={v => { setMealOrdered(v); if (!v) setMealConfirmed(false); }}
          yesLabel="✓ Ordered"
          noLabel="✗ Skipped"
        />
        {mealOrdered === true && (
          <div className="ot-subsection">
            <div className="ot-sub-label">Was it delivered?</div>
            <OTToggle
              value={mealConfirmed}
              onChange={setMealConfirmed}
              yesLabel="✓ Received"
              noLabel="Not yet"
            />
          </div>
        )}
      </div>

      {/* Sleep */}
      <div className="ot-section">
        <div className="ot-section-label">😴 Sleep target</div>
        <OTToggle
          value={sleep}
          onChange={setSleep}
          yesLabel="✓ Hit it"
          noLabel="✗ Missed"
        />
      </div>

      {error && <div className="ot-error">{error}</div>}

      <button
        className="btn btn-primary ot-submit"
        onClick={handleSubmit}
        disabled={!canSubmit || submitting}
      >
        {submitting ? 'Saving…' : 'Submit Outcomes'}
      </button>
    </div>
  );
}

// ── Outcome Tracking shared helpers ──────────────────────────────

function _badgeClass(value, lowerIsBetter = false) {
  const effective = lowerIsBetter ? (11 - value) : value;
  if (effective >= 7.5) return 'slider-badge-good';
  if (effective >= 4.5) return 'slider-badge-ok';
  return 'slider-badge-bad';
}

function SliderRow({ label, icon, value, onChange, min = 1, max = 10, step = 0.5, lowerIsBetter = false }) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="checkin-slider-row">
      <div className="checkin-slider-header">
        <span className="checkin-slider-label">
          {icon && <span className="slider-icon">{icon}</span>}
          {label}
        </span>
        <span className={`slider-badge ${_badgeClass(value, lowerIsBetter)}`}>{value}</span>
      </div>
      <div className="slider-track-wrap">
        <div className="slider-track-fill" style={{ width: `${pct}%` }} />
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="checkin-slider"
        />
      </div>
      <div className="checkin-slider-scale">
        <span>{min === 0 ? '0 hrs' : min}</span>
        <span>{max}{min === 0 ? ' hrs' : ''}</span>
      </div>
    </div>
  );
}

// ── DailyCheckin ──────────────────────────────────────────────────

function DailyCheckin({ userId, onSubmitted }) {
  const [mood,       setMood]       = useState(7);
  const [energy,     setEnergy]     = useState(7);
  const [stress,     setStress]     = useState(4);
  const [sleep,      setSleep]      = useState(7.5);
  const [notes,      setNotes]      = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [saved,      setSaved]      = useState(null); // {mood, energy, stress, sleep}
  const [error,      setError]      = useState('');

  const handleSubmit = async () => {
    setSubmitting(true); setError('');
    try {
      const res = await fetch(`${API}/api/outcomes/daily`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, mood, energy, stress, sleep_hours: sleep, notes: notes || null }),
      });
      if (res.ok) {
        setSaved({ mood, energy, stress, sleep });
        if (onSubmitted) onSubmitted();
      } else {
        const d = await res.json();
        setError(d.detail || 'Failed to save.');
      }
    } catch { setError('Connection error.'); }
    finally { setSubmitting(false); }
  };

  if (saved) {
    return (
      <div className="checkin-saved">
        <div className="checkin-saved-header">
          <span className="checkin-saved-icon">✓</span>
          <span className="checkin-saved-title">Today's check-in saved</span>
        </div>
        <div className="checkin-saved-values">
          <span>Mood <strong>{saved.mood}</strong></span>
          <span>Energy <strong>{saved.energy}</strong></span>
          <span>Stress <strong>{saved.stress}</strong></span>
          <span>Sleep <strong>{saved.sleep}h</strong></span>
        </div>
        <button className="btn-link" onClick={() => setSaved(null)}>Update</button>
      </div>
    );
  }

  return (
    <div className="checkin-form">
      <SliderRow label="Mood"   icon="😊" value={mood}   onChange={setMood}   lowerIsBetter={false} />
      <SliderRow label="Energy" icon="⚡" value={energy} onChange={setEnergy} lowerIsBetter={false} />
      <SliderRow label="Stress" icon="😤" value={stress} onChange={setStress} lowerIsBetter={true}  />
      <SliderRow label="Sleep"  icon="😴" value={sleep}  onChange={setSleep}  lowerIsBetter={false} min={0} max={12} />
      <div className="checkin-notes-row">
        <label className="checkin-slider-label">Notes <span className="checkin-optional">(optional)</span></label>
        <textarea
          className="checkin-notes"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="How did you feel today?"
          rows={2}
        />
      </div>
      {error && <div className="checkin-error">{error}</div>}
      <button className="btn btn-primary checkin-submit" onClick={handleSubmit} disabled={submitting}>
        {submitting ? 'Saving…' : 'Save Daily Check-In'}
      </button>
    </div>
  );
}

// ── WeeklyCheckin ─────────────────────────────────────────────────

function WeeklyCheckin({ userId, onSubmitted }) {
  const [weight,     setWeight]     = useState('');
  const [waist,      setWaist]      = useState('');
  const [bf,         setBf]         = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [saved,      setSaved]      = useState(null);
  const [error,      setError]      = useState('');

  const handleSubmit = async () => {
    if (!weight && !waist && !bf) { setError('Enter at least one measurement.'); return; }
    setSubmitting(true); setError('');
    try {
      const res = await fetch(`${API}/api/outcomes/weekly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          weight_kg:           weight ? parseFloat(weight) : null,
          waist_cm:            waist  ? parseFloat(waist)  : null,
          body_fat_percentage: bf     ? parseFloat(bf)     : null,
        }),
      });
      if (res.ok) {
        setSaved({ weight, waist, bf });
        if (onSubmitted) onSubmitted();
      } else {
        const d = await res.json();
        setError(d.detail || 'Failed to save.');
      }
    } catch { setError('Connection error.'); }
    finally { setSubmitting(false); }
  };

  if (saved) {
    const parts = [
      saved.weight && `${saved.weight} kg`,
      saved.waist  && `Waist ${saved.waist} cm`,
      saved.bf     && `Body fat ${saved.bf}%`,
    ].filter(Boolean);
    return (
      <div className="checkin-saved">
        <div className="checkin-saved-header">
          <span className="checkin-saved-icon">✓</span>
          <span className="checkin-saved-title">Measurements saved</span>
        </div>
        <div className="checkin-saved-values">
          {parts.map((p, i) => <span key={i}>{p}</span>)}
        </div>
        <button className="btn-link" onClick={() => setSaved(null)}>Update</button>
      </div>
    );
  }

  return (
    <div className="checkin-form">
      <div className="checkin-input-row">
        <label className="checkin-input-label"><span className="slider-icon">⚖️</span> Weight (kg)</label>
        <input type="number" step="0.1" className="checkin-number-input" value={weight}
          onChange={e => setWeight(e.target.value)} placeholder="e.g. 82.5" />
      </div>
      <div className="checkin-input-row">
        <label className="checkin-input-label"><span className="slider-icon">📏</span> Waist (cm)</label>
        <input type="number" step="0.5" className="checkin-number-input" value={waist}
          onChange={e => setWaist(e.target.value)} placeholder="e.g. 90" />
      </div>
      <div className="checkin-input-row">
        <label className="checkin-input-label"><span className="slider-icon">📊</span> Body Fat % <span className="checkin-optional">(optional)</span></label>
        <input type="number" step="0.1" className="checkin-number-input" value={bf}
          onChange={e => setBf(e.target.value)} placeholder="e.g. 18.5" />
      </div>
      {error && <div className="checkin-error">{error}</div>}
      <button className="btn btn-primary checkin-submit" onClick={handleSubmit} disabled={submitting}>
        {submitting ? 'Saving…' : 'Save Measurements'}
      </button>
    </div>
  );
}

// ── ProgressDashboard ─────────────────────────────────────────────

function ProgressDashboard({ userId, data, onCheckinSubmit }) {
  const [tab, setTab] = useState('checkin');

  function TrendCard({ label, icon, value, higherIsBetter = true, unit = '' }) {
    if (value == null) return (
      <div className="progress-card progress-card-empty">
        <div className="progress-card-icon">{icon}</div>
        <div className="progress-card-label">{label}</div>
        <div className="progress-card-value">—</div>
        <div className="progress-card-direction">No data yet</div>
      </div>
    );
    const positive = higherIsBetter ? value > 0 : value < 0;
    const neutral  = Math.abs(value) < 0.05;
    const cls      = neutral ? 'progress-card-stable' : positive ? 'progress-card-up' : 'progress-card-down';
    const arrow    = neutral ? '→' : positive ? '↑' : '↓';
    const sign     = value > 0 ? '+' : '';
    return (
      <div className={`progress-card ${cls}`}>
        <div className="progress-card-icon">{icon}</div>
        <div className="progress-card-label">{label}</div>
        <div className="progress-card-value">{sign}{value.toFixed(1)}{unit}</div>
        <div className="progress-card-direction">{arrow} {neutral ? 'Stable' : positive ? 'Improving' : 'Declining'}</div>
      </div>
    );
  }

  function EffBar({ label, score }) {
    const isNoData = score === 50;
    const color    = isNoData ? 'var(--text-muted)' : score >= 70 ? 'var(--success)' : score >= 50 ? '#f59e0b' : 'var(--danger)';
    const note     = isNoData ? 'No data yet' : score >= 70 ? 'Effective' : score >= 50 ? 'Moderate' : 'Needs work';
    return (
      <div className="eff-item">
        <div className="eff-item-header">
          <span className="eff-label">{label}</span>
          <div className="eff-right">
            <span className="eff-note" style={{ color }}>{note}</span>
            <span className="eff-score" style={{ color }}>{isNoData ? '—' : `${score}%`}</span>
          </div>
        </div>
        <div className="adh-bar">
          <div className="adh-fill" style={{ width: `${isNoData ? 0 : score}%`, background: color }} />
        </div>
      </div>
    );
  }

  const trends        = data?.trends;
  const insights      = data?.insights;
  const effectiveness = data?.effectiveness;
  const hasTrendData  = trends && Object.values(trends).some(v => v != null);

  return (
    <div className="weekly-plan-section">
      <div className="weekly-plan-eyebrow">My Progress</div>
      <div className="card progress-dashboard">

        {/* Tabs */}
        <div className="pd-tabs">
          <button className={`pd-tab ${tab === 'checkin'  ? 'pd-tab-active' : ''}`} onClick={() => setTab('checkin')}>
            Check-In
          </button>
          <button className={`pd-tab ${tab === 'progress' ? 'pd-tab-active' : ''}`} onClick={() => setTab('progress')}>
            Trends &amp; Insights
          </button>
        </div>

        {/* ── Check-In Tab ── */}
        {tab === 'checkin' && (
          <div className="pd-checkin-panels">
            <div className="pd-panel">
              <div className="pd-panel-title">Daily Check-In</div>
              <p className="pd-panel-sub">How are you feeling today?</p>
              <DailyCheckin userId={userId} onSubmitted={onCheckinSubmit} />
            </div>
            <div className="pd-panel">
              <div className="pd-panel-title">Weekly Measurements</div>
              <p className="pd-panel-sub">Track physical progress once a week.</p>
              <WeeklyCheckin userId={userId} onSubmitted={onCheckinSubmit} />
            </div>
          </div>
        )}

        {/* ── Progress Tab ── */}
        {tab === 'progress' && (
          <div className="pd-progress-tab">

            {/* Insights summary banner */}
            {insights?.summary && (
              <div className="pd-summary-banner">
                <span className="pd-summary-icon">✦</span>
                <span>{insights.summary}</span>
              </div>
            )}

            {/* Trend Cards — always shown */}
            <div className="progress-section-title">Health Trends <span className="progress-section-sub">7-day avg vs previous 7 days</span></div>
            <div className="progress-grid">
              <TrendCard label="Mood"   icon="😊" value={trends?.mood_change}   higherIsBetter={true}  />
              <TrendCard label="Energy" icon="⚡" value={trends?.energy_change} higherIsBetter={true}  />
              <TrendCard label="Stress" icon="😤" value={trends?.stress_change} higherIsBetter={false} />
              <TrendCard label="Sleep"  icon="😴" value={trends?.sleep_change}  higherIsBetter={true}  unit=" h" />
              <TrendCard label="Weight" icon="⚖️" value={trends?.weight_change} higherIsBetter={false} unit=" kg" />
              <TrendCard label="Waist"  icon="📏" value={trends?.waist_change}  higherIsBetter={false} unit=" cm" />
            </div>

            {/* Wins / Warnings */}
            {insights && (insights.wins.length > 0 || insights.warnings.length > 0) && (
              <div className="progress-insights">
                {insights.wins.length > 0 && (
                  <div className="progress-wins">
                    <div className="progress-wins-title">Wins</div>
                    {insights.wins.map((w, i) => <div key={i} className="progress-win-item">✓ {w}</div>)}
                  </div>
                )}
                {insights.warnings.length > 0 && (
                  <div className="progress-warnings">
                    <div className="progress-warnings-title">Watch Out</div>
                    {insights.warnings.map((w, i) => <div key={i} className="progress-warning-item">⚠ {w}</div>)}
                  </div>
                )}
              </div>
            )}

            {/* Decision Effectiveness */}
            {effectiveness && (
              <>
                <div className="progress-section-title" style={{ marginTop: '0.25rem' }}>
                  Decision Effectiveness <span className="progress-section-sub">are recommendations working?</span>
                </div>
                <div className="eff-grid">
                  <EffBar label="Recovery Days → Lower Stress next day"    score={effectiveness.recovery_day_effectiveness} />
                  <EffBar label="Confirmed Meals → More Energy next day"   score={effectiveness.meal_effectiveness} />
                  <EffBar label="Completed Workouts → Better Mood next day" score={effectiveness.workout_effectiveness} />
                </div>
              </>
            )}

            {/* Empty state */}
            {!hasTrendData && !insights?.wins?.length && !insights?.warnings?.length && (
              <div className="pd-empty-state">
                <div className="pd-empty-icon">📈</div>
                <div className="pd-empty-title">No trend data yet</div>
                <div className="pd-empty-sub">
                  Complete daily check-ins for at least two weeks to see your health trends here.
                </div>
                <button className="btn-link" onClick={() => setTab('checkin')}>
                  Go to Check-In →
                </button>
              </div>
            )}

          </div>
        )}

      </div>
    </div>
  );
}

// ── AI Visibility Components ─────────────────────────────────────

function AIDecisionHeader({ dr, profile, workoutTime, lunchTime, dinnerTime }) {
  const cyclePhase = dr.cycle_phase?.phase;
  return (
    <div className="ai-dh-wrap">
      <div className="ai-dh-eyebrow">🧠 Today's AI Decision</div>
      <div className="ai-dh-top-row">
        <div className="ai-dh-left">
          <div className="ai-dh-title">Your {DAY_LABELS[dr.day_type]} Day Plan</div>
          <div className="ai-dh-sub">{profile.name} · {profile.ziel} · {profile.ernaehrung}</div>
          <div className="ai-dh-badges">
            <span className={`day-badge ${DAY_COLORS[dr.day_type]}`}>{DAY_LABELS[dr.day_type]} Day</span>
            {cyclePhase && cyclePhase !== 'unknown' && (
              <span className={`cycle-phase-badge ${cyclePhase}`}>{CYCLE_PHASE_LABELS[cyclePhase]}</span>
            )}
          </div>
        </div>
        <div className="ai-dh-confidence">
          <div className="ai-dh-conf-value">{dr.recovery_score}</div>
          <div className="ai-dh-conf-label">AI Confidence</div>
        </div>
      </div>
      <div className="ai-dh-analyzed">
        <span className="ai-dh-analyzed-label">AI analyzed:</span>
        <div className="ai-dh-chips">
          {[
            { icon: '😴', label: 'Sleep',    value: `${profile.sleep_hours}h`   },
            { icon: '😤', label: 'Stress',   value: `${profile.stress_level}/10` },
            { icon: '📅', label: 'Meetings', value: `${profile.meetings_count}`  },
            { icon: '⚡', label: 'Recovery', value: `${dr.recovery_score}/100`  },
          ].map(a => (
            <div key={a.label} className="ai-dh-chip">
              <span className="ai-dh-chip-icon">{a.icon}</span>
              <span className="ai-dh-chip-label">{a.label}</span>
              <span className="ai-dh-chip-val">{a.value}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="ai-dh-schedule">
        {[
          { icon: '🏋️', label: 'Workout', time: workoutTime },
          { icon: '🌅', label: 'Lunch',   time: lunchTime   },
          { icon: '🍽',  label: 'Dinner',  time: dinnerTime  },
        ].map(m => (
          <div key={m.label} className="ai-dh-sched-item">
            <span className="ai-dh-sched-icon">{m.icon}</span>
            <div>
              <div className="ai-dh-sched-label">{m.label}</div>
              <div className="ai-dh-sched-time">{m.time}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AIReasoningCard({ dr, profile }) {
  const [open, setOpen] = useState(false);
  const inputs = [
    { icon: '😴', label: 'Sleep',    value: `${profile.sleep_hours}h`,    note: parseFloat(profile.sleep_hours) >= 7 ? '✓ Good' : '⚠ Below target' },
    { icon: '😤', label: 'Stress',   value: `${profile.stress_level}/10`,  note: parseInt(profile.stress_level) <= 4 ? '✓ Low' : parseInt(profile.stress_level) <= 7 ? '⚠ Moderate' : '✕ High' },
    { icon: '📅', label: 'Meetings', value: `${profile.meetings_count}`,    note: parseInt(profile.meetings_count) <= 2 ? '✓ Light' : '⚠ Busy' },
    { icon: '⚡', label: 'Recovery', value: `${dr.recovery_score}/100`,     note: dr.recovery_score >= 70 ? '✓ High' : dr.recovery_score >= 40 ? '⚠ Medium' : '✕ Low' },
  ];
  return (
    <div className="ai-reasoning-card">
      <button className="ai-rc-toggle" onClick={() => setOpen(o => !o)}>
        <span>🤔</span>
        <span className="ai-rc-toggle-text">Why did the AI decide this?</span>
        <span className="ai-rc-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="ai-rc-body">
          <div className="ai-rc-input-grid">
            {inputs.map(inp => (
              <div key={inp.label} className="ai-rc-input-item">
                <span className="ai-rc-inp-icon">{inp.icon}</span>
                <div className="ai-rc-inp-mid">
                  <div className="ai-rc-inp-label">{inp.label}</div>
                  <div className="ai-rc-inp-value">{inp.value}</div>
                </div>
                <div className="ai-rc-inp-note">{inp.note}</div>
              </div>
            ))}
          </div>
          {dr.explanation && <p className="ai-rc-explanation">{dr.explanation}</p>}
          {dr.coaching_message && <div className="ai-rc-coaching">{dr.coaching_message}</div>}
          <ScoreDriversCard drivers={dr.score_drivers} />
        </div>
      )}
    </div>
  );
}

function AIMemoryPanel({ adherenceData }) {
  const hasData = adherenceData?.adherence?.total_days_tracked > 0;
  if (!hasData) {
    return (
      <div className="ai-memory-panel ai-memory-empty">
        <div className="ai-mp-header">
          <span>🧠</span>
          <span className="ai-mp-title">What the AI Learned</span>
        </div>
        <div className="ai-mp-placeholder">Complete your first day to help the AI adapt to your patterns.</div>
      </div>
    );
  }
  const { adherence, streaks, ai_insight, at_risk } = adherenceData;
  return (
    <div className="ai-memory-panel">
      <div className="ai-mp-header">
        <span>🧠</span>
        <span className="ai-mp-title">What the AI Learned</span>
        <span className="ai-mp-days">{adherence.total_days_tracked}d</span>
      </div>
      <div className="ai-mp-stats">
        {[
          { icon: '🔥', val: streaks.current_streak,           lbl: 'Streak'  },
          { icon: '💪', val: `${adherence.workout_adherence}%`, lbl: 'Workout' },
          { icon: '🍽', val: `${adherence.meal_adherence}%`,    lbl: 'Meals'   },
          { icon: '😴', val: `${adherence.sleep_adherence}%`,   lbl: 'Sleep'   },
        ].map(s => (
          <div key={s.lbl} className="ai-mp-stat">
            <div className="ai-mp-stat-icon">{s.icon}</div>
            <div className="ai-mp-stat-val">{s.val}</div>
            <div className="ai-mp-stat-lbl">{s.lbl}</div>
          </div>
        ))}
      </div>
      {ai_insight && (
        <div className="ai-mp-insight"><span>✦</span><span>{ai_insight}</span></div>
      )}
      {at_risk?.at_risk && (
        <div className="ai-mp-risk">⚠ Plan adapted to reduce friction today.</div>
      )}
    </div>
  );
}

function AIEvolutionTimeline({ adherenceData }) {
  const days = adherenceData?.adherence?.total_days_tracked ?? 0;
  const steps = [
    { minDays: 0,  label: 'Week 1', desc: 'Learning your patterns'  },
    { minDays: 7,  label: 'Week 2', desc: 'Detected preferences'    },
    { minDays: 14, label: 'Week 3', desc: 'Personalizing intensity' },
    { minDays: 21, label: 'Week 4', desc: 'Full optimization mode'  },
  ];
  return (
    <div className="ai-evolution-card">
      <div className="ai-ev-header">
        <span>📈</span>
        <span className="ai-ev-title">AI Evolution</span>
      </div>
      <div className="ai-ev-list">
        {steps.map((s, i) => {
          const reached  = days >= s.minDays;
          const isCurrent = reached && (i === steps.length - 1 || days < steps[i + 1].minDays);
          return (
            <div key={i} className={`ai-ev-item ${reached ? 'ai-ev-done' : 'ai-ev-future'} ${isCurrent ? 'ai-ev-current' : ''}`}>
              <div className="ai-ev-dot" />
              {i < steps.length - 1 && <div className="ai-ev-connector" />}
              <div className="ai-ev-content">
                <div className="ai-ev-week">{s.label}</div>
                <div className="ai-ev-desc">{s.desc}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const FEEDBACK_REASONS = {
  workout: ['Too difficult', 'Too easy', 'No time', 'Wrong type', 'Stress misread', 'Other'],
  meal:    ['Wrong cuisine', 'Too expensive', 'Dietary issue', 'Portion size', 'Bad timing', 'Other'],
};

function AIFeedback({ type }) {
  const [rating,    setRating]    = useState(null);
  const [reason,    setReason]    = useState('');
  const [submitted, setSubmitted] = useState(false);

  if (submitted) return (
    <div className="ai-feedback ai-fb-done">
      {rating === 'up' ? '👍 Thanks! AI noted.' : `👎 Feedback noted: "${reason}". AI will adapt.`}
    </div>
  );

  return (
    <div className="ai-feedback">
      <span className="ai-fb-prompt">Was this helpful?</span>
      <button className={`ai-fb-btn ${rating === 'up' ? 'ai-fb-up' : ''}`} onClick={() => { setRating('up'); setSubmitted(true); }}>👍</button>
      <button className={`ai-fb-btn ${rating === 'down' ? 'ai-fb-down' : ''}`} onClick={() => setRating(r => r === 'down' ? null : 'down')}>👎</button>
      {rating === 'down' && (
        <div className="ai-fb-reasons">
          {FEEDBACK_REASONS[type].map(r => (
            <button key={r} className={`ai-fb-reason ${reason === r ? 'ai-fb-reason-sel' : ''}`} onClick={() => setReason(r)}>{r}</button>
          ))}
          {reason && <button className="btn btn-primary ai-fb-submit" onClick={() => setSubmitted(true)}>Send</button>}
        </div>
      )}
    </div>
  );
}

function WeeklySnapshot({ planText, pdfLink, profile }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="weekly-plan-section">
      <div className="weekly-plan-eyebrow">Dein Wochenplan</div>
      <div className="card weekly-snapshot-card">
        <div className="ws-snap-header">
          <div>
            <div className="ws-snap-title">Weekly Training &amp; Nutrition Plan</div>
            <div className="ws-snap-sub">{profile.name} · {profile.training_days}×/week · {profile.ziel} · {profile.ernaehrung}</div>
          </div>
          <div className="ws-snap-actions">
            {pdfLink && (
              <a href={pdfLink} className="pdf-link" target="_blank" rel="noopener noreferrer" download>PDF</a>
            )}
            <button className="btn btn-ghost" onClick={() => setOpen(o => !o)}>
              {open ? 'Schließen' : 'Vollplan anzeigen'}
            </button>
          </div>
        </div>
        {!open && (
          <div className="ws-snap-preview">
            <span className="ws-snap-preview-icon">📋</span>
            <span className="ws-snap-preview-text">KI-generierter {profile.training_days}-Tage Trainingsplan mit personalisierten Ernährungsempfehlungen</span>
            <button className="btn-link" onClick={() => setOpen(true)}>Vollplan anzeigen →</button>
          </div>
        )}
        {open && (
          <div className="plan-content" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(planText) }} />
        )}
      </div>
    </div>
  );
}

function AIWorkoutCard({ workout, breakdown, scheduleTime, token, dr }) {
  const [sessionActive, setSessionActive] = useState(false);
  const [expanded,      setExpanded]      = useState(false);
  const [reasonOpen,    setReasonOpen]    = useState(false);

  if (sessionActive) {
    return <WorkoutSession workout={workout} token={token} onClose={() => setSessionActive(false)} />;
  }

  const dayGoals = {
    performance: { goal: 'Maximum Performance', benefits: ['Power Output', 'Strength', 'Peak Intensity'] },
    recovery:    { goal: 'Active Recovery',      benefits: ['Mobility', 'Circulation', 'Mental Reset'] },
    normal:      { goal: 'Consistent Progress',  benefits: ['Strength', 'Fat Burn', 'Consistency'] },
  };
  const { goal, benefits } = dayGoals[dr.day_type] || dayGoals.normal;
  const confidence = Math.min(100, Math.round((dr.recovery_score + (dr.energy_score ?? dr.recovery_score)) / 2));

  return (
    <div className="ai-workout-card">
      <div className="ai-wc-top">
        <div className="ai-wc-eyebrow">🤖 Today's AI Workout</div>
        <div className="ai-wc-conf-badge">
          <span className="ai-wc-conf-val">{confidence}%</span>
          <span className="ai-wc-conf-lbl">Match</span>
        </div>
      </div>
      <div className="ai-wc-name">{workout.name}</div>
      <div className="ai-wc-goal-row">
        <span className="ai-wc-goal-label">Goal:</span>
        <span className="ai-wc-goal-value">{goal}</span>
      </div>
      <div className="ai-wc-benefits">
        {benefits.map(b => <span key={b} className="ai-wc-benefit">{b}</span>)}
      </div>
      <div className="workout-action-meta" style={{ marginTop: '0.75rem' }}>
        <span className="wa-meta-chip">{scheduleTime}</span>
        <span className="wa-meta-chip">{breakdown.total_minutes} min</span>
        <span className="wa-meta-chip">{workout.intensity}</span>
        <span className="wa-meta-chip">{workout.level}</span>
      </div>
      <div className="duration-chips" style={{ marginTop: '0.75rem' }}>
        <span className="duration-chip warmup">Aufwärmen {breakdown.warmup_minutes} min</span>
        <span className="duration-chip main">Training {breakdown.main_training_minutes} min</span>
        <span className="duration-chip cooldown">Cooldown {breakdown.cooldown_minutes} min</span>
      </div>
      <div className="ai-wc-why-section">
        <button className="ai-wc-why-btn" onClick={() => setReasonOpen(o => !o)}>
          💡 Why this workout? {reasonOpen ? '▲' : '▼'}
        </button>
        {reasonOpen && (
          <div className="ai-wc-why-body">
            {workout.description
              ? <p>{workout.description}</p>
              : dr.coaching_message && <p>{dr.coaching_message}</p>
            }
          </div>
        )}
      </div>
      <div className="ai-wc-actions">
        <button className="btn-start-workout" onClick={() => setSessionActive(true)}>Training starten</button>
        <button className="btn-show-exercises" onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Übungen schließen' : 'Übungen anzeigen'}
        </button>
      </div>
      {expanded && (
        <div className="exercise-list" style={{ marginTop: '1rem' }}>
          {workout.exercises.map((ex, i) => (
            <div key={i} className="exercise-item exercise-item-rich">
              <div className="exercise-header">
                <span className="exercise-num">{i + 1}</span>
                <span className="exercise-name-text">{ex.exercise_name}</span>
                <span className="exercise-sets-badge">{ex.sets}× {ex.reps_or_duration}</span>
              </div>
              <div className="exercise-detail-row">
                <span className="exercise-instruction">{ex.instructions}</span>
              </div>
              {ex.common_mistakes && (
                <div className="exercise-mistake-row">
                  <span className="mistake-label">Häufiger Fehler:</span> {ex.common_mistakes}
                </div>
              )}
              <div className="exercise-video-row">
                <a className="exercise-video-btn" href={ex.video_url} target="_blank" rel="noopener noreferrer">Video ansehen</a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AIMealDeliveryCard({ label, meal, deliveryTime, mealType, token, dr, goal }) {
  function getAIReason() {
    if (dr.day_type === 'performance' && meal.protein_g >= 30) return 'High protein supports today\'s strength goals';
    if (dr.day_type === 'recovery') return 'Light macros match today\'s recovery focus';
    if (meal.protein_g >= 25) return 'Supports muscle protein synthesis';
    return `Matched to your ${goal} targets`;
  }
  return (
    <div className="ai-meal-wrap">
      <div className="ai-meal-reason">
        <span className="ai-meal-reason-icon">🤖</span>
        <span>{getAIReason()}</span>
      </div>
      <MealDeliveryCard label={label} meal={meal} deliveryTime={deliveryTime} mealType={mealType} token={token} />
    </div>
  );
}

// ── WorkoutSession ────────────────────────────────────────────────

function WorkoutSession({ workout, token, onClose }) {
  const exercises  = workout.exercises || [];
  const totalSets  = exercises.reduce((s, ex) => s + ex.sets, 0);

  // ── Session state ──────────────────────────────────────────────
  const [sessionId,        setSessionId]        = useState(null);
  const [exIdx,            setExIdx]            = useState(0);
  const [setsDoneInEx,     setSetsDoneInEx]     = useState({}); // { exIdx → sets completed }
  const [totalSetsDone,    setTotalSetsDone]    = useState(0);
  const [completedExNames, setCompletedExNames] = useState([]);

  // ── Timers ─────────────────────────────────────────────────────
  const [elapsed,         setElapsed]         = useState(0);    // counts up (seconds)
  const [countdown,       setCountdown]       = useState(null); // null | number
  const [countdownActive, setCountdownActive] = useState(false);

  // ── Status ─────────────────────────────────────────────────────
  const [done,      setDone]      = useState(false);
  const [result,    setResult]    = useState(null);
  const [finishing, setFinishing] = useState(false);

  // ── Derived ────────────────────────────────────────────────────
  const currentEx         = exercises[exIdx] || {};
  const setsDoneInCurrent = setsDoneInEx[exIdx] || 0;
  const allSetsInExDone   = setsDoneInCurrent >= (currentEx.sets || 1);
  const timerSecs         = parseTimerSecs(currentEx.reps_or_duration || '');
  const progressPct       = totalSets > 0 ? Math.round((totalSetsDone / totalSets) * 100) : 0;

  // ── Start session on mount ─────────────────────────────────────
  useEffect(() => {
    let mounted = true;
    fetch(`${API}/api/workouts/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workout_id: workout.id, workout_name: workout.name, total_sets: totalSets }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (mounted && data) setSessionId(data.session_id); })
      .catch(() => {});
    return () => { mounted = false; };
  }, []);

  // ── Elapsed timer ──────────────────────────────────────────────
  useEffect(() => {
    if (done) return;
    const id = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(id);
  }, [done]);

  // ── Countdown timer ────────────────────────────────────────────
  useEffect(() => {
    if (!countdownActive) return;
    const id = setInterval(() => {
      setCountdown(c => {
        if (c <= 1) { setCountdownActive(false); return 0; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [countdownActive]);

  // ── Helpers ────────────────────────────────────────────────────
  const resetCountdownFor = (idx) => {
    const secs = parseTimerSecs(exercises[idx]?.reps_or_duration || '');
    setCountdown(secs);
    setCountdownActive(false);
  };

  const goToEx = (idx) => {
    setExIdx(idx);
    resetCountdownFor(idx);
  };

  // ── Mark set complete ──────────────────────────────────────────
  const markSetComplete = () => {
    const newDone    = setsDoneInCurrent + 1;
    const exName     = currentEx.exercise_name;
    const exFinished = newDone >= currentEx.sets;

    setSetsDoneInEx(prev => ({ ...prev, [exIdx]: newDone }));
    setTotalSetsDone(prev => prev + 1);
    if (exFinished) {
      setCompletedExNames(prev => prev.includes(exName) ? prev : [...prev, exName]);
    }
    if (timerSecs) { setCountdown(timerSecs); setCountdownActive(false); }

    // Sync to backend (fire-and-forget)
    if (sessionId) {
      fetch(`${API}/api/workouts/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, exercise_name: exName, sets_completed: 1 }),
      }).catch(() => {});
    }
  };

  // ── Finish workout ─────────────────────────────────────────────
  const finishWorkout = async () => {
    setFinishing(true);
    const sid         = sessionId || 'local';
    const finalExNames = [...completedExNames];
    try {
      const res = await fetch(`${API}/api/workouts/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sid,
          duration_seconds: elapsed,
          intensity: workout.intensity || 'moderate',
          completed_exercises: finalExNames,
          completed_sets: totalSetsDone,
        }),
      });
      setResult(res.ok ? await res.json() : null);
    } catch { setResult(null); }
    finally { setDone(true); setFinishing(false); }
  };

  // ── Completion screen ──────────────────────────────────────────
  if (done) {
    const kcal     = result?.calories_estimate ?? Math.round(elapsed / 60 * 6);
    const exCount  = result?.completed_exercises?.length ?? completedExNames.length;
    const setsCount = result?.completed_sets ?? totalSetsDone;
    const msg      = MOTIVATIONAL_MESSAGES[setsCount % MOTIVATIONAL_MESSAGES.length];
    return (
      <div className="workout-session ws-completion-screen">
        <div className="ws-completion-icon">✓</div>
        <div className="ws-completion-title">Workout abgeschlossen!</div>
        <p className="ws-completion-msg">{msg}</p>
        <div className="ws-completion-stats">
          <div className="ws-stat">
            <div className="ws-stat-value">{fmtTime(result?.duration_seconds ?? elapsed)}</div>
            <div className="ws-stat-label">Dauer</div>
          </div>
          <div className="ws-stat">
            <div className="ws-stat-value">{exCount}</div>
            <div className="ws-stat-label">Übungen</div>
          </div>
          <div className="ws-stat">
            <div className="ws-stat-value">{setsCount}</div>
            <div className="ws-stat-label">Sätze</div>
          </div>
          <div className="ws-stat">
            <div className="ws-stat-value">{kcal}</div>
            <div className="ws-stat-label">kcal (est.)</div>
          </div>
        </div>
        <button className="btn btn-primary ws-done-btn" onClick={onClose}>Fertig</button>
      </div>
    );
  }

  // ── Active session ─────────────────────────────────────────────
  return (
    <div className="workout-session">

      {/* Header */}
      <div className="ws-header">
        <div>
          <div className="ws-label">Workout Session</div>
          <div className="ws-title">{workout.name}</div>
        </div>
        <div className="ws-header-right">
          <span className="ws-elapsed">{fmtTime(elapsed)}</span>
          <button className="ws-exit-btn" onClick={finishWorkout} disabled={finishing}>
            {finishing ? '…' : 'Beenden'}
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="ws-progress-wrap">
        <div className="ws-progress-bar">
          <div className="ws-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <span className="ws-progress-text">
          Übung {exIdx + 1}/{exercises.length} · {totalSetsDone}/{totalSets} Sätze
        </span>
      </div>

      {/* Exercise card */}
      <div className="ws-exercise-card">
        <div className="ws-ex-index">Übung {exIdx + 1} von {exercises.length}</div>
        <div className="ws-ex-name">{currentEx.exercise_name}</div>

        <div className="ws-set-row">
          {allSetsInExDone ? (
            <span className="ws-set-badge ws-set-done">✓ Alle Sätze erledigt</span>
          ) : (
            <span className="ws-set-badge">
              Satz {setsDoneInCurrent + 1} von {currentEx.sets}
            </span>
          )}
          <span className="ws-reps-badge">{currentEx.reps_or_duration}</span>
        </div>

        {/* Instructions */}
        <div className="ws-instructions">
          <div className="ws-section-label">Ausführung</div>
          <p>{currentEx.instructions}</p>
        </div>

        {/* Common mistakes */}
        {currentEx.common_mistakes && (
          <div className="ws-mistakes">
            <div className="ws-section-label">Häufiger Fehler</div>
            <p>{currentEx.common_mistakes}</p>
          </div>
        )}

        {/* Countdown timer (timed exercises only) */}
        {timerSecs != null && (
          <div className="ws-timer-section">
            <div className="ws-countdown">{fmtTime(countdown ?? timerSecs)}</div>
            {!countdownActive ? (
              <button className="ws-timer-btn" onClick={() => { setCountdown(timerSecs); setCountdownActive(true); }}>
                {countdown === 0 ? 'Nochmal' : 'Timer starten'}
              </button>
            ) : (
              <button className="ws-timer-btn ws-timer-stop" onClick={() => { setCountdownActive(false); }}>
                Stopp
              </button>
            )}
          </div>
        )}

        {/* Video link */}
        {currentEx.video_url && (
          <a className="ws-video-link" href={currentEx.video_url} target="_blank" rel="noopener noreferrer">
            Video ansehen →
          </a>
        )}
      </div>

      {/* Controls */}
      <div className="ws-controls">
        <div className="ws-nav">
          <button className="ws-nav-btn" onClick={() => goToEx(exIdx - 1)} disabled={exIdx === 0}>
            ← Zurück
          </button>
          <button className="ws-nav-btn" onClick={() => goToEx(exIdx + 1)} disabled={exIdx === exercises.length - 1}>
            Weiter →
          </button>
        </div>
        <button
          className={`ws-set-btn${allSetsInExDone ? ' ws-set-btn-done' : ''}`}
          onClick={markSetComplete}
          disabled={allSetsInExDone}
        >
          {allSetsInExDone ? '✓ Alle Sätze erledigt' : 'Satz abschließen'}
        </button>
      </div>

      {/* Exercise nav dots */}
      <div className="ws-ex-dots">
        {exercises.map((ex, i) => {
          const exDone    = (setsDoneInEx[i] || 0) >= ex.sets;
          const isCurrent = i === exIdx;
          return (
            <button
              key={i}
              className={`ws-ex-dot${isCurrent ? ' ws-dot-current' : ''}${exDone ? ' ws-dot-done' : ''}`}
              onClick={() => goToEx(i)}
              title={ex.exercise_name}
            />
          );
        })}
      </div>
    </div>
  );
}

// ── WorkoutCard ───────────────────────────────────────────────────

function WorkoutCard({ workout, breakdown, scheduleTime, token }) {
  const [sessionActive, setSessionActive] = useState(false);
  const [expanded,      setExpanded]      = useState(false);

  if (sessionActive) {
    return (
      <WorkoutSession
        workout={workout}
        token={token}
        onClose={() => setSessionActive(false)}
      />
    );
  }

  return (
    <div className="workout-action-card">
      <div className="workout-action-header">
        <div>
          <div className="workout-action-label">Heutiges Training</div>
          <div className="workout-action-name">{workout.name}</div>
          <div className="workout-action-meta">
            <span className="wa-meta-chip">{scheduleTime}</span>
            <span className="wa-meta-chip">{breakdown.total_minutes} min</span>
            <span className="wa-meta-chip">{workout.intensity}</span>
            <span className="wa-meta-chip">{workout.level}</span>
          </div>
        </div>
        <button className="btn-start-workout" onClick={() => setSessionActive(true)}>
          Training starten
        </button>
      </div>

      <div className="duration-chips" style={{ marginTop: '0.75rem' }}>
        <span className="duration-chip warmup">Aufwärmen {breakdown.warmup_minutes} min</span>
        <span className="duration-chip main">Training {breakdown.main_training_minutes} min</span>
        <span className="duration-chip cooldown">Cooldown {breakdown.cooldown_minutes} min</span>
        <span className="duration-chip total">Gesamt {breakdown.total_minutes} min</span>
      </div>

      {workout.description && (
        <p className="workout-description">{workout.description}</p>
      )}

      <button className="btn-show-exercises" onClick={() => setExpanded(e => !e)}>
        {expanded ? 'Übungen schließen' : 'Übungen anzeigen'}
      </button>

      {expanded && (
        <div className="exercise-list" style={{ marginTop: '1rem' }}>
          {workout.exercises.map((ex, i) => (
            <div key={i} className="exercise-item exercise-item-rich">
              <div className="exercise-header">
                <span className="exercise-num">{i + 1}</span>
                <span className="exercise-name-text">{ex.exercise_name}</span>
                <span className="exercise-sets-badge">{ex.sets}× {ex.reps_or_duration}</span>
              </div>
              <div className="exercise-detail-row">
                <span className="exercise-instruction">{ex.instructions}</span>
              </div>
              {ex.common_mistakes && (
                <div className="exercise-mistake-row">
                  <span className="mistake-label">Häufiger Fehler:</span> {ex.common_mistakes}
                </div>
              )}
              <div className="exercise-video-row">
                <a className="exercise-video-btn" href={ex.video_url} target="_blank" rel="noopener noreferrer">
                  Video ansehen
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const LOCATION_OPTIONS = [
  { value: 'buero',      label: 'Büro',       api: 'office'  },
  { value: 'zuhause',    label: 'Zuhause',    api: 'home'    },
  { value: 'unterwegs',  label: 'Unterwegs',  api: 'travel'  },
];

function MealDeliveryCard({ label, meal, deliveryTime, mealType, token }) {
  const [location, setLocation]   = useState('buero');
  const [loading, setLoading]     = useState(false);
  const [orderId, setOrderId]     = useState(null);
  const [error, setError]         = useState('');

  const handleConfirm = async () => {
    setLoading(true); setError('');
    const apiLocation = LOCATION_OPTIONS.find(o => o.value === location)?.api || 'office';
    try {
      const res = await fetch(`${API}/api/orders/daily-delivery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          meal_id: meal.id,
          meal_slot: mealType,
          delivery_location: apiLocation,
          scheduled_time: deliveryTime,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail || 'Fehler bei der Bestätigung.');
      } else {
        const data = await res.json();
        setOrderId(data.order_id);
      }
    } catch {
      setError('Verbindung zum Server fehlgeschlagen.');
    } finally {
      setLoading(false);
    }
  };

  const confirmed = !!orderId;

  return (
    <div className={`delivery-card ${confirmed ? 'delivery-confirmed' : ''}`}>
      <div className="delivery-card-top">
        <span className="delivery-meal-type">{label}</span>
        <span className="delivery-time-badge">{deliveryTime}</span>
      </div>

      <div className="meal-partner">{meal.provider}</div>
      <div className="meal-name" style={{ paddingRight: 0 }}>{meal.name}</div>

      <div className="meal-macros" style={{ margin: '0.625rem 0' }}>
        <span className="macro-badge">{meal.calories} kcal</span>
        <span className="macro-badge">P {meal.protein_g}g</span>
        <span className="macro-badge">C {meal.carbs_g}g</span>
        <span className="macro-badge">F {meal.fat_g}g</span>
      </div>

      <div className="delivery-price">{meal.price_eur.toFixed(2)} EUR</div>

      {!confirmed ? (
        <>
          <div className="location-picker">
            {LOCATION_OPTIONS.map(opt => (
              <button
                key={opt.value}
                className={`location-btn ${location === opt.value ? 'active' : ''}`}
                onClick={() => setLocation(opt.value)}
                disabled={loading}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {error && <div style={{ fontSize: '0.8rem', color: 'var(--danger)', marginBottom: '0.5rem' }}>{error}</div>}
          <button className="btn-confirm-delivery" onClick={handleConfirm} disabled={loading}>
            {loading ? 'Wird bestätigt …' : 'Lieferung bestätigen'}
          </button>
        </>
      ) : (
        <div className="delivery-confirmed-state">
          <span className="delivery-check">✓</span>
          <span>Bestätigt · {LOCATION_OPTIONS.find(o => o.value === location)?.label} · {deliveryTime} · #{orderId}</span>
        </div>
      )}
    </div>
  );
}

// ── CalendarEventsSection ─────────────────────────────────────────

function CalendarEventsSection({ events, onChange }) {
  const [newTitle,        setNewTitle]        = useState('');
  const [newStart,        setNewStart]        = useState('');
  const [newEnd,          setNewEnd]          = useState('');
  const [selectedPreset,  setSelectedPreset]  = useState(null);

  const canAdd = newTitle.trim() && newStart && newEnd && newStart < newEnd;

  const addEvent = () => {
    if (!canAdd) return;
    onChange([...events, { title: newTitle.trim(), start_time: newStart, end_time: newEnd }]);
    setNewTitle(''); setNewStart(''); setNewEnd('');
    setSelectedPreset(null);
  };

  const removeEvent = (idx) => onChange(events.filter((_, i) => i !== idx));

  const selectPreset = (p) => { setSelectedPreset(p.id); onChange(p.events); };
  const clearAll     = ()  => { setSelectedPreset(null);  onChange([]);       };

  const dayLoad     = calcDayLoad(events);
  const aiAdj       = calcAIAdjustments(events);

  const LOAD_CONFIG = {
    low:    { label: '🟢 Wenig Belastung',     cls: 'cal-load-low'    },
    medium: { label: '🟡 Moderate Belastung',  cls: 'cal-load-medium' },
    high:   { label: '🔴 Hohe Belastung',      cls: 'cal-load-high'   },
  };

  return (
    <div className="cal-section">

      {/* ── Header ── */}
      <div className="cal-section-header">
        <div className="cal-section-title">📅 Wie sieht dein Tag heute aus?</div>
        <div className="cal-section-sub">Die AI passt Training, Mahlzeiten und Regeneration automatisch an deinen Tagesablauf an.</div>
        {events.length > 0 && (
          <span className={`cal-day-load ${LOAD_CONFIG[dayLoad].cls}`}>
            {LOAD_CONFIG[dayLoad].label}
          </span>
        )}
      </div>

      {/* ── Presets ── */}
      <div className="cal-presets">
        <button className="cal-preset-btn cal-preset-clear" onClick={clearAll}>
          Leeren
        </button>
        {CALENDAR_PRESETS.map(p => (
          <button
            key={p.id}
            className={`cal-preset-btn ${selectedPreset === p.id ? 'cal-preset-active' : ''}`}
            onClick={() => selectPreset(p)}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* ── Event list ── */}
      {events.length > 0 && (
        <div className="cal-events-list">
          {events.map((ev, i) => (
            <div key={i} className="cal-event-item">
              <span className="cal-event-title">{ev.title}</span>
              <span className="cal-event-time">{ev.start_time} – {ev.end_time}</span>
              <button className="cal-event-remove" onClick={() => removeEvent(i)} title="Entfernen">×</button>
            </div>
          ))}
        </div>
      )}

      {/* ── AI Adjustment Card ── */}
      {aiAdj && (
        <div className="cal-ai-card">
          <div className="cal-ai-card-header">
            <span>🤖</span>
            <span className="cal-ai-card-title">AI Anpassungen</span>
          </div>
          <div className="cal-ai-scenario">{aiAdj.scenario}</div>
          <div className="cal-ai-adj-label">Änderungen:</div>
          <div className="cal-ai-adjustments">
            {aiAdj.adjustments.map((adj, i) => (
              <div key={i} className="cal-ai-adj-item">
                <span className="cal-ai-adj-check">✓</span>
                <span>{adj}</span>
              </div>
            ))}
          </div>

          {/* Before / After */}
          <div className="cal-ba-compare">
            <div className="cal-ba-col">
              <div className="cal-ba-col-label">Ohne Anpassung</div>
              <div className="cal-ba-item">
                <span className="cal-ba-icon">🏋️</span>
                <div>
                  <div className="cal-ba-name">Workout</div>
                  <div className="cal-ba-val">55 min</div>
                </div>
              </div>
              <div className="cal-ba-item">
                <span className="cal-ba-icon">🌅</span>
                <div>
                  <div className="cal-ba-name">Lunch</div>
                  <div className="cal-ba-val">12:30</div>
                </div>
              </div>
            </div>
            <div className="cal-ba-arrow">→</div>
            <div className="cal-ba-col cal-ba-after">
              <div className="cal-ba-col-label">Mit AI Anpassung</div>
              <div className="cal-ba-item">
                <span className="cal-ba-icon">🏋️</span>
                <div>
                  <div className="cal-ba-name">Workout</div>
                  <div className={`cal-ba-val ${aiAdj.workoutAfter !== '55 min' ? 'cal-ba-changed' : ''}`}>{aiAdj.workoutAfter}</div>
                </div>
              </div>
              <div className="cal-ba-item">
                <span className="cal-ba-icon">🌅</span>
                <div>
                  <div className="cal-ba-name">Lunch</div>
                  <div className={`cal-ba-val ${aiAdj.lunchAfter !== '12:30' ? 'cal-ba-changed' : ''}`}>{aiAdj.lunchAfter}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Add event form ── */}
      <div className="cal-add-form-wrap">
        <div className="cal-add-form-label">➕ Termin hinzufügen</div>
        <div className="cal-add-form">
          <input
            type="text"
            placeholder="z. B. Kundentermin, Team Meeting, Reise …"
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addEvent()}
          />
          <input type="time" value={newStart} onChange={e => setNewStart(e.target.value)} />
          <input type="time" value={newEnd}   onChange={e => setNewEnd(e.target.value)}   />
          <button className="cal-add-btn" onClick={addEvent} disabled={!canAdd}>
            + Hinzufügen
          </button>
        </div>
      </div>

      {/* ── Google Calendar CTA (Phase 2 placeholder) ── */}
      <div className="cal-gcal-cta">
        <div className="cal-gcal-icon">🔗</div>
        <div className="cal-gcal-text">
          <div className="cal-gcal-title">Google Calendar verbinden</div>
          <div className="cal-gcal-sub">Die AI erkennt automatisch Meetings, Reisen und freie Trainingsfenster – kein manuelles Eintragen nötig.</div>
        </div>
        <button className="cal-gcal-btn" disabled>Bald verfügbar</button>
      </div>

    </div>
  );
}

// ── StepIndicator ─────────────────────────────────────────────────

function StepIndicator({ step }) {
  return (
    <div className="steps">
      {STEPS.map((s, i) => {
        const num  = i + 1;
        const active = num === step;
        const done   = num < step;
        return (
          <div key={s.label} className={`step-item ${active ? 'active' : ''} ${done ? 'done' : ''}`}>
            <div className="step-dot">{done ? '✓' : num}</div>
            <div className="step-label">{s.label}</div>
          </div>
        );
      })}
    </div>
  );
}

// ── AuthScreen ────────────────────────────────────────────────────

function AuthScreen({ onAuth }) {
  const [mode, setMode]     = useState('login');
  const [form, setForm]     = useState({ name: '', email: '', password: '' });
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    setLoading(true); setError('');
    const endpoint = mode === 'login' ? '/auth/login' : '/auth/register';
    const body = mode === 'login'
      ? { email: form.email, password: form.password }
      : { name: form.name, email: form.email, password: form.password };
    try {
      const res    = await fetch(`${API}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const result = await res.json();
      if (res.ok) { onAuth(result.access_token, result.user); }
      else        { setError(result.detail || 'Fehler aufgetreten.'); }
    } catch { setError('Verbindung zum Server fehlgeschlagen.'); }
    finally { setLoading(false); }
  };

  const switchMode = (next) => { setMode(next); setError(''); };
  const isDisabled = loading || !form.email || !form.password || (mode === 'register' && !form.name);

  return (
    <main className="main">
      <div className="card" style={{ maxWidth: 420, margin: '0 auto' }}>
        <div className="step-heading">
          <h2>{mode === 'login' ? 'Willkommen zurück' : 'Konto erstellen'}</h2>
          <p>{mode === 'login' ? 'Melde dich an, um deinen Tagesplan zu starten.' : 'Erstelle dein NurtureAI-Konto – kostenlos.'}</p>
        </div>
        {mode === 'register' && (
          <div className="form-group">
            <label>Vorname</label>
            <input name="name" value={form.name} onChange={handleChange} placeholder="z. B. Max" />
          </div>
        )}
        <div className="form-group">
          <label>E-Mail</label>
          <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="deine@email.de" />
        </div>
        <div className="form-group">
          <label>Passwort</label>
          <input name="password" type="password" value={form.password} onChange={handleChange} placeholder="Mindestens 8 Zeichen" />
        </div>
        {error && <div className="auth-error">{error}</div>}
        <button className="btn btn-primary" style={{ width: '100%', marginTop: '0.5rem' }} onClick={handleSubmit} disabled={isDisabled}>
          {loading ? '...' : mode === 'login' ? 'Anmelden' : 'Registrieren'}
        </button>
        <div className="auth-toggle">
          {mode === 'login'
            ? (<>Noch kein Konto?{' '}<button onClick={() => switchMode('register')}>Registrieren</button></>)
            : (<>Bereits registriert?{' '}<button onClick={() => switchMode('login')}>Anmelden</button></>)}
        </div>
      </div>
    </main>
  );
}

// ── App ───────────────────────────────────────────────────────────

export default function App() {
  const [token, setToken]       = useState(() => localStorage.getItem('nurture_token'));
  const [authUser, setAuthUser] = useState(() => {
    const saved = localStorage.getItem('nurture_user');
    return saved ? JSON.parse(saved) : null;
  });

  const [step, setStep] = useState(1);

  const [profile, setProfile] = useState({
    name:    authUser?.name || '',
    gender:  '',
    alter:   '',
    gewicht: '',
    ziel:        '',
    ernaehrung:  '',
    supplements: false,
    level:       '',
    training_days: '',
    equipment:     '',
    sleep_hours:                       '',
    stress_level:                      5,
    meetings_count:                    '',
    available_training_window_minutes: '',
    cycle_tracking_enabled:  false,
    last_period_start_date:  '',
    average_cycle_length:    28,
    average_period_length:   5,
    profession: '',
  });

  const [painAreas, setPainAreas] = useState([]);   // [{area, severity}]
  const [calendarEvents, setCalendarEvents] = useState([]);

  const [results,    setResults]    = useState(null);
  const [generating, setGenerating] = useState(false);
  const [genError,   setGenError]   = useState('');

  const [selectedSkus,      setSelectedSkus]      = useState(new Set());
  const [orderConfirmation,  setOrderConfirmation] = useState(null);
  const [orderLoading,       setOrderLoading]      = useState(false);
  const [adherenceData,      setAdherenceData]     = useState(null);
  const [progressData,       setProgressData]      = useState(null);

  // ── Auth ───────────────────────────────────────────────────────

  const handleAuth = (newToken, user) => {
    localStorage.setItem('nurture_token', newToken);
    localStorage.setItem('nurture_user', JSON.stringify(user));
    setToken(newToken);
    setAuthUser(user);
  };

  const handleLogout = () => {
    localStorage.removeItem('nurture_token');
    localStorage.removeItem('nurture_user');
    setToken(null); setAuthUser(null);
    setStep(1); setResults(null);
    setSelectedSkus(new Set()); setOrderConfirmation(null);
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setProfile(prev => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  // ── Dashboard refresh ──────────────────────────────────────────

  const refreshDashboard = (userId) => {
    fetch(`${API}/api/users/${encodeURIComponent(userId)}/dashboard`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setAdherenceData(d); })
      .catch(() => {});
  };

  const refreshProgressDashboard = (userId) => {
    const enc = encodeURIComponent(userId);
    Promise.all([
      fetch(`${API}/api/users/${enc}/outcome-trends`),
      fetch(`${API}/api/users/${enc}/outcome-insights`),
      fetch(`${API}/api/users/${enc}/decision-effectiveness`),
    ])
      .then(([r1, r2, r3]) => Promise.all([
        r1.ok ? r1.json() : null,
        r2.ok ? r2.json() : null,
        r3.ok ? r3.json() : null,
      ]))
      .then(([trends, insights, effectiveness]) => {
        setProgressData({ trends, insights, effectiveness });
      })
      .catch(() => {});
  };

  // ── Generate ───────────────────────────────────────────────────

  const handleGenerate = async () => {
    setGenerating(true); setGenError('');
    setResults(null); setSelectedSkus(new Set()); setOrderConfirmation(null);

    const authHeaders = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };

    const cycleProfile = profile.gender === 'female' ? {
      gender:                 'female',
      cycle_tracking_enabled: profile.cycle_tracking_enabled,
      last_period_start_date: profile.cycle_tracking_enabled && profile.last_period_start_date ? profile.last_period_start_date : null,
      average_cycle_length:   parseInt(profile.average_cycle_length) || 28,
      average_period_length:  parseInt(profile.average_period_length) || 5,
    } : null;

    const windowMinutes = profile.available_training_window_minutes !== ''
      ? parseInt(profile.available_training_window_minutes) : null;

    try {
      const [planRes, dailyRes] = await Promise.all([
        fetch(`${API}/formdata`, {
          method: 'POST', headers: authHeaders,
          body: JSON.stringify({
            name: profile.name, geschlecht: GENDER_TO_GESCHLECHT[profile.gender],
            alter: parseInt(profile.alter), gewicht: parseInt(profile.gewicht),
            ziel: profile.ziel, ernaehrung: profile.ernaehrung,
            supplements: profile.supplements, level: profile.level,
            training_days: parseInt(profile.training_days), equipment: profile.equipment,
          }),
        }),
        fetch(`${API}/api/health-autopilot/daily-decision`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_profile: {
              name: profile.name,
              ziel: profile.ziel,
              ernaehrung: profile.ernaehrung,
              level: profile.level,
              cycle_profile: cycleProfile,
              profession: profile.profession || null,
              pain_areas: painAreas.length > 0 ? painAreas : [],
            },
            daily_context: {
              sleep_hours: parseFloat(profile.sleep_hours),
              stress_level: parseInt(profile.stress_level),
              meetings_count: parseInt(profile.meetings_count),
              available_training_window_minutes: windowMinutes,
              calendar_events: calendarEvents,
            },
          }),
        }),
      ]);

      if (planRes.status === 401) { handleLogout(); return; }

      const planData  = await planRes.json();
      const dailyData = await dailyRes.json();

      if (planData.status === 'ok' && dailyRes.ok) {
        setResults({ planText: planData.plan, pdfLink: `${API}${planData.pdf_url}`, matchedMeals: planData.matched_meals || [], dailyResult: dailyData });
        setStep('results');
        refreshDashboard(profile.name);
        refreshProgressDashboard(profile.name);
      } else {
        setGenError(planData.status !== 'ok'
          ? 'Fehler beim Wochenplan: ' + (planData.message || 'Unbekannter Fehler.')
          : 'Fehler beim Tagesautopilot: ' + (dailyData.detail || 'Unbekannter Fehler.'));
      }
    } catch { setGenError('Verbindung zum Server fehlgeschlagen. Bitte erneut versuchen.'); }
    finally { setGenerating(false); }
  };

  // ── Order ──────────────────────────────────────────────────────

  const toggleMeal = (id) => {
    setSelectedSkus(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const handleOrder = async () => {
    if (selectedSkus.size === 0) return;
    setOrderLoading(true); setOrderConfirmation(null);
    const authHeaders = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };
    try {
      const res    = await fetch(`${API}/order`, { method: 'POST', headers: authHeaders, body: JSON.stringify({ user_name: profile.name, meal_ids: Array.from(selectedSkus) }) });
      if (res.status === 401) { handleLogout(); return; }
      const result = await res.json();
      if (result.status === 'ok') { setOrderConfirmation(result); setSelectedSkus(new Set()); }
      else { alert('Bestellfehler: ' + result.detail); }
    } catch { alert('Verbindung zum Server fehlgeschlagen.'); }
    finally { setOrderLoading(false); }
  };

  const handleRestart = () => {
    setStep(1); setResults(null); setSelectedSkus(new Set());
    setAdherenceData(null); setProgressData(null);
    setOrderConfirmation(null); setCalendarEvents([]); setPainAreas([]);
  };

  const step1Valid = profile.name && profile.gender && profile.alter && profile.gewicht;
  const step2Valid = profile.ziel && profile.ernaehrung && profile.level;
  const step3Valid = profile.training_days && profile.sleep_hours !== '' && profile.meetings_count !== '';

  const selectedMeals = results ? results.matchedMeals.filter(m => selectedSkus.has(m.id)) : [];
  const cartTotal     = selectedMeals.reduce((sum, m) => sum + m.price_eur, 0);

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo">Nurture<span>AI</span></div>
          <div className="tagline">Dein persönlicher AI Health Autopilot</div>
          {token && authUser && (
            <div className="header-user">
              <span>{authUser.name}</span>
              <button className="btn btn-ghost" style={{ padding: '0.4rem 0.875rem', fontSize: '0.825rem' }} onClick={handleLogout}>
                Abmelden
              </button>
            </div>
          )}
        </div>
      </header>

      {!token ? (
        <AuthScreen onAuth={handleAuth} />
      ) : (
        <main className="main">

          {/* Generating spinner */}
          {generating && (
            <div className="card">
              <div className="spinner-wrapper" style={{ padding: '4rem 1rem' }}>
                <div className="spinner" />
                <div style={{ textAlign: 'center' }}>
                  <strong>Dein Tages- und Wochenplan wird erstellt …</strong>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                    Das dauert ca. 15 Sekunden
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── Form steps 1–3 ── */}
          {!generating && step !== 'results' && (
            <div className="card">
              <StepIndicator step={step} />

              {step === 1 && (
                <>
                  <div className="step-heading">
                    <h2>Erzähl uns von dir</h2>
                    <p>Deine Basisdaten personalisieren Tagesplan und Wochenplan.</p>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Vorname</label>
                      <input name="name" value={profile.name} onChange={handleChange} placeholder="z. B. Max" />
                    </div>
                    <div className="form-group">
                      <label>Geschlecht</label>
                      <select name="gender" value={profile.gender} onChange={handleChange}>
                        <option value="">Bitte wählen</option>
                        <option value="male">Männlich</option>
                        <option value="female">Weiblich</option>
                        <option value="other">Divers</option>
                      </select>
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Alter</label>
                      <input name="alter" type="number" value={profile.alter} onChange={handleChange} placeholder="z. B. 32" />
                    </div>
                    <div className="form-group">
                      <label>Gewicht (kg)</label>
                      <input name="gewicht" type="number" value={profile.gewicht} onChange={handleChange} placeholder="z. B. 80" />
                    </div>
                  </div>
                  <div className="form-group" style={{ marginTop: '1.25rem' }}>
                    <label>Beruf <span className="form-optional">(optional — verbessert die Gesundheitsanalyse)</span></label>
                    <select name="profession" value={profile.profession} onChange={handleChange}>
                      <option value="">Beruf auswählen …</option>
                      {PROFESSION_OPTIONS.map(p => (
                        <option key={p.id} value={p.id}>{p.label}</option>
                      ))}
                    </select>
                  </div>

                  <div className="form-group" style={{ marginTop: '1rem' }}>
                    <label>Körperbeschwerden <span className="form-optional">(optional — Schmerzstellen auswählen)</span></label>
                    <PainAreaSelector selectedAreas={painAreas} onChange={setPainAreas} />
                  </div>

                  <div className="form-actions">
                    <span />
                    <button className="btn btn-primary" onClick={() => setStep(2)} disabled={!step1Valid}>Weiter →</button>
                  </div>
                </>
              )}

              {step === 2 && (
                <>
                  <div className="step-heading">
                    <h2>Deine Ziele &amp; Ernährung</h2>
                    <p>Damit wir deinen Ernährungsplan und deine Mahlzeiten optimal abstimmen.</p>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Mein Ziel</label>
                      <select name="ziel" value={profile.ziel} onChange={handleChange}>
                        <option value="">Bitte wählen</option>
                        <option value="Muskelaufbau">Muskelaufbau</option>
                        <option value="Fettabbau">Fettabbau</option>
                        <option value="Gesund bleiben">Gesund bleiben</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Ernährungsstil</label>
                      <select name="ernaehrung" value={profile.ernaehrung} onChange={handleChange}>
                        <option value="">Bitte wählen</option>
                        <option value="Mischkost">Mischkost</option>
                        <option value="Vegan">Vegan</option>
                        <option value="Vegetarisch">Vegetarisch</option>
                        <option value="Halal">Halal</option>
                      </select>
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Trainingslevel</label>
                    <select name="level" value={profile.level} onChange={handleChange}>
                      <option value="">Bitte wählen</option>
                      <option value="Einsteiger">Einsteiger</option>
                      <option value="Fortgeschrittene">Fortgeschrittene</option>
                      <option value="Advanced">Advanced</option>
                    </select>
                  </div>
                  <label className="checkbox-group">
                    <input type="checkbox" name="supplements" checked={profile.supplements} onChange={handleChange} />
                    <span>Supplement-Empfehlungen gewünscht</span>
                  </label>
                  <div className="form-actions">
                    <button className="btn btn-ghost" onClick={() => setStep(1)}>← Zurück</button>
                    <button className="btn btn-primary" onClick={() => setStep(3)} disabled={!step2Valid}>Weiter →</button>
                  </div>
                </>
              )}

              {step === 3 && (
                <>
                  <div className="step-heading">
                    <h2>Training &amp; Tageskontext</h2>
                    <p>Trainingsdetails für den Wochenplan und der heutige Kontext für die Tagesanalyse.</p>
                  </div>

                  <div className="form-section-label">Training</div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Trainingstage pro Woche</label>
                      <select name="training_days" value={profile.training_days} onChange={handleChange}>
                        <option value="">Bitte wählen</option>
                        {[1, 2, 3, 4, 5, 6].map(n => (<option key={n} value={n}>{n}x pro Woche</option>))}
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Verfügbares Equipment (optional)</label>
                      <input name="equipment" value={profile.equipment} onChange={handleChange} placeholder="z. B. Kurzhanteln, kein Equipment" />
                    </div>
                  </div>

                  <div className="form-section-label" style={{ marginTop: '1.25rem' }}>Heute</div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Schlafstunden letzte Nacht</label>
                      <input name="sleep_hours" type="number" min="0" max="24" step="0.5" value={profile.sleep_hours} onChange={handleChange} placeholder="z. B. 6.5" />
                    </div>
                    <div className="form-group">
                      <label>Meetings heute</label>
                      <input name="meetings_count" type="number" min="0" value={profile.meetings_count} onChange={handleChange} placeholder="z. B. 4" />
                    </div>
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Verfügbares Zeitfenster Training (min, optional)</label>
                      <input name="available_training_window_minutes" type="number" min="5" max="240" value={profile.available_training_window_minutes} onChange={handleChange} placeholder="z. B. 45" />
                    </div>
                    <div className="form-group" />
                  </div>
                  <div className="form-group">
                    <label>Stresslevel &mdash; <strong style={{ color: 'var(--primary)' }}>{profile.stress_level}/10</strong></label>
                    <input type="range" name="stress_level" min="1" max="10" value={profile.stress_level} onChange={handleChange} className="stress-slider" />
                    <div className="stress-labels"><span>Entspannt</span><span>Extrem</span></div>
                  </div>

                  <div className="form-section-label" style={{ marginTop: '1.25rem' }}>Kalender heute</div>
                  <CalendarEventsSection events={calendarEvents} onChange={setCalendarEvents} />

                  {profile.gender === 'female' && (
                    <div className="cycle-section">
                      <div className="cycle-section-title">Zyklustracking</div>
                      <label className="checkbox-group" style={{ marginBottom: '0.75rem' }}>
                        <input type="checkbox" name="cycle_tracking_enabled" checked={profile.cycle_tracking_enabled} onChange={handleChange} />
                        <span>Zyklusphase in Trainingsempfehlung einbeziehen</span>
                      </label>
                      {profile.cycle_tracking_enabled && (
                        <>
                          <div className="form-row">
                            <div className="form-group">
                              <label>Letzter Periodenstart</label>
                              <input type="date" name="last_period_start_date" value={profile.last_period_start_date} onChange={handleChange} />
                            </div>
                            <div className="form-group">
                              <label>Zykluslänge (Tage)</label>
                              <input type="number" name="average_cycle_length" min="21" max="45" value={profile.average_cycle_length} onChange={handleChange} />
                            </div>
                          </div>
                          <div className="form-row">
                            <div className="form-group">
                              <label>Periodendauer (Tage)</label>
                              <input type="number" name="average_period_length" min="1" max="10" value={profile.average_period_length} onChange={handleChange} />
                            </div>
                            <div className="form-group" />
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  {genError && <div className="auth-error" style={{ marginTop: '1rem' }}>{genError}</div>}

                  <div className="form-actions">
                    <button className="btn btn-ghost" onClick={() => setStep(2)}>← Zurück</button>
                    <button className="btn btn-primary" onClick={handleGenerate} disabled={!step3Valid}>
                      Plan &amp; Tagesanalyse erstellen
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ── Results ── */}
          {!generating && step === 'results' && results && (() => {
            const dr = results.dailyResult;
            const cyclePhase    = dr?.cycle_phase?.phase;
            const scheduleItems = dr?.schedule || [];
            const workoutTime   = dr?.workout_time          || '18:00';
            const lunchTime     = dr?.lunch_delivery_time   || '12:30';
            const dinnerTime    = dr?.dinner_delivery_time  || '19:30';

            return (
              <>
                {/* Results bar */}
                <div className="results-bar">
                  <div className="results-bar-info">
                    <span className="results-bar-name">{profile.name}</span>
                    <span className="results-bar-meta">
                      {GENDER_LABEL[profile.gender]} · {profile.ziel} · {profile.ernaehrung} · {profile.level}
                      &nbsp;·&nbsp; {profile.sleep_hours}h Schlaf · Stress {profile.stress_level}/10
                    </span>
                  </div>
                  <button className="btn btn-ghost" style={{ fontSize: '0.825rem', padding: '0.35rem 0.875rem', whiteSpace: 'nowrap' }} onClick={handleRestart}>
                    Neu starten
                  </button>
                </div>

                {/* ══ OCCUPATIONAL HEALTH ADVISOR ══ */}
                {dr && dr.health_advisor_message && (
                  <HealthAdvisorPanel
                    message={dr.health_advisor_message}
                    profession={dr.occupation_profile?.profession_display}
                  />
                )}

                {dr && (dr.occupation_profile || painAreas.length > 0) && (
                  <OccupationalRiskCard
                    occProfile={dr.occupation_profile}
                    painAreas={painAreas}
                  />
                )}

                {dr && dr.health_priorities?.length > 0 && (
                  <HealthPriorityStack priorities={dr.health_priorities} />
                )}

                {dr && dr.why_this_matters && (
                  <WhyThisMattersCard data={dr.why_this_matters} />
                )}

                {/* ══ AI COMMAND CENTER ══ */}
                {dr && (
                  <div className="ai-command-center">

                    {/* Step 1: AI Decision Header */}
                    <AIDecisionHeader
                      dr={dr}
                      profile={profile}
                      workoutTime={workoutTime}
                      lunchTime={lunchTime}
                      dinnerTime={dinnerTime}
                    />

                    {/* Step 2: AI Reasoning (collapsible) */}
                    <AIReasoningCard dr={dr} profile={profile} />

                    {/* Step 3+9: AI Memory + Evolution row */}
                    <div className="ai-panels-row">
                      <AIMemoryPanel adherenceData={adherenceData} />
                      <AIEvolutionTimeline adherenceData={adherenceData} />
                    </div>

                    {/* Cycle phase */}
                    {cyclePhase && cyclePhase !== 'unknown' && (
                      <CyclePhasePanel phase={cyclePhase} />
                    )}

                    {/* Schedule warnings */}
                    {dr.schedule_warnings?.length > 0 && (
                      <div className="schedule-warnings">
                        {dr.schedule_warnings.map((w, i) => (
                          <div key={i} className="schedule-warning-item">{w}</div>
                        ))}
                      </div>
                    )}

                    {/* Today's Actions */}
                    <div className="ai-actions-section">
                      <div className="ai-actions-eyebrow">Today's Actions</div>

                      <ScheduleTimeline schedule={scheduleItems} />

                      {/* Step 4: AI Workout Card */}
                      {dr.selected_workout && (
                        <>
                          <AIWorkoutCard
                            workout={dr.selected_workout}
                            breakdown={dr.workout_duration_breakdown}
                            scheduleTime={workoutTime}
                            token={token}
                            dr={dr}
                          />
                          {/* Step 8: Workout feedback */}
                          <AIFeedback type="workout" />
                        </>
                      )}

                      {/* Step 5: AI Meal Cards */}
                      <div className="cmd-meals-section">
                        <div className="cmd-meals-label">Deine Mahlzeiten heute</div>
                        <div className="cmd-meals-grid">
                          {dr.selected_lunch && (
                            <AIMealDeliveryCard
                              label="Mittagessen"
                              meal={dr.selected_lunch}
                              deliveryTime={lunchTime}
                              mealType="lunch"
                              token={token}
                              dr={dr}
                              goal={profile.ziel}
                            />
                          )}
                          {dr.selected_dinner && (
                            <AIMealDeliveryCard
                              label="Abendessen"
                              meal={dr.selected_dinner}
                              deliveryTime={dinnerTime}
                              mealType="dinner"
                              token={token}
                              dr={dr}
                              goal={profile.ziel}
                            />
                          )}
                        </div>
                        {/* Step 8: Meal feedback */}
                        <AIFeedback type="meal" />
                      </div>

                      {/* Outcome Tracker */}
                      {dr.record_id && (
                        <OutcomeTracker
                          recordId={dr.record_id}
                          recommendedDuration={dr.workout_duration_breakdown?.total_minutes ?? 45}
                          onSubmitted={() => refreshDashboard(profile.name)}
                        />
                      )}
                    </div>

                  </div>
                )}

                {/* ══ Step 7: PROGRESS SECTION ══ */}
                <AdherenceDashboard data={adherenceData} />
                <ProgressDashboard
                  userId={profile.name}
                  data={progressData}
                  onCheckinSubmit={() => refreshProgressDashboard(profile.name)}
                />

                {/* ══ Step 6: WEEKLY SNAPSHOT (collapsed by default) ══ */}
                <WeeklySnapshot
                  planText={results.planText}
                  pdfLink={results.pdfLink}
                  profile={profile}
                />

                {/* ══ MEAL ORDERING ══ */}
                {results.matchedMeals.length > 0 && (
                  <div className="weekly-plan-section">
                    <div className="weekly-plan-eyebrow">Mahlzeiten bestellen</div>
                    <div className="section-subtitle" style={{ marginBottom: '1rem' }}>
                      Passend zu deinem Ziel – wähle aus, was du diese Woche bestellen möchtest.
                    </div>
                    <div className="meals-grid">
                      {results.matchedMeals.map((meal) => {
                        const selected = selectedSkus.has(meal.id);
                        return (
                          <div key={meal.id} className={`meal-card ${selected ? 'selected' : ''}`} onClick={() => toggleMeal(meal.id)}>
                            {selected && <div className="meal-check">✓</div>}
                            <div className="meal-partner">{meal.provider}</div>
                            <div className="meal-name">{meal.name}</div>
                            <div className="meal-macros">
                              <span className="macro-badge">{meal.calories} kcal</span>
                              <span className="macro-badge">P {meal.protein_g}g</span>
                              <span className="macro-badge">C {meal.carbs_g}g</span>
                              <span className="macro-badge">F {meal.fat_g}g</span>
                            </div>
                            <div className="meal-footer">
                              <span className="meal-price">{meal.price_eur.toFixed(2)} EUR</span>
                              <span className="meal-sku">{meal.id}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {selectedSkus.size > 0 && (
                      <div className="cart-bar">
                        <div className="cart-summary">
                          <div className="cart-count">{selectedSkus.size} Mahlzeit{selectedSkus.size > 1 ? 'en' : ''} ausgewählt</div>
                          <div className="cart-total">Gesamtbetrag: <strong>{cartTotal.toFixed(2)} EUR</strong></div>
                        </div>
                        <button className="btn btn-order" onClick={handleOrder} disabled={orderLoading}>
                          {orderLoading ? 'Wird bestellt …' : 'Bestellung aufgeben'}
                        </button>
                      </div>
                    )}

                    {orderConfirmation && (
                      <div className="order-confirm">
                        <div className="order-confirm-title">Bestellung bestätigt</div>
                        <div className="order-confirm-id">Bestellnummer: <strong>{orderConfirmation.order_id}</strong></div>
                        <ul className="order-items">
                          {orderConfirmation.ordered_meals.map(m => (
                            <li key={m.id}>
                              <span>{m.name}<span className="order-partner"> · {m.provider}</span></span>
                              <span>{m.price_eur.toFixed(2)} EUR</span>
                            </li>
                          ))}
                        </ul>
                        <div className="order-total">Gesamt: {orderConfirmation.total_price_eur.toFixed(2)} EUR</div>
                      </div>
                    )}
                  </div>
                )}
              </>
            );
          })()}

        </main>
      )}
    </div>
  );
}
