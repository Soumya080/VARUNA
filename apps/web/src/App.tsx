import { useState, useEffect } from 'react';
import { AlertTriangle, Clock, ShieldAlert, Activity, FileText, Anchor } from 'lucide-react';

interface Case {
  case_id: string;
  status: string;
  created_at: string;
}

interface CaseDetails extends Case {
  scientific_status: string;
  n_artifacts: number;
  n_events: number;
}

interface EventItem {
  event_id: string;
  event_type: string;
  timestamp: string;
  actor: string;
}

interface ArtifactItem {
  id: string;
  type: string;
  produced_by: string;
  created_at: string;
}

export default function App() {
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [caseDetails, setCaseDetails] = useState<CaseDetails | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('http://localhost:8000/v1/cases')
      .then(res => res.json())
      .then(data => setCases(data.items || []))
      .catch(err => console.error("Failed to load cases", err));
  }, []);

  useEffect(() => {
    if (!selectedCase) return;
    setLoading(true);
    
    Promise.all([
      fetch(`http://localhost:8000/v1/cases/${selectedCase}`).then(r => r.json()),
      fetch(`http://localhost:8000/v1/events?case_id=${selectedCase}`).then(r => r.json()),
      fetch(`http://localhost:8000/v1/cases/${selectedCase}/artifacts`).then(r => r.json())
    ]).then(([details, eventsData, artifactsData]) => {
      setCaseDetails(details);
      setEvents(eventsData.events || []);
      setArtifacts(artifactsData.items || []);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, [selectedCase]);

  return (
    <div className="flex h-screen w-full bg-slate-950 overflow-hidden text-slate-200">
      
      {/* Sidebar: Case List */}
      <div className="w-80 glass-panel border-r border-slate-800 flex flex-col relative z-20">
        <div className="p-6 border-b border-slate-800 bg-slate-900/50">
          <div className="flex items-center gap-3 mb-2">
            <Anchor className="text-blue-400 w-6 h-6 animate-pulse" />
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 to-indigo-300 bg-clip-text text-transparent">
              VARUNA GRID
            </h1>
          </div>
          <p className="text-xs text-slate-400 font-medium">National Marine Pollution Watch</p>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4 ml-2">Active Cases</h2>
          
          {cases.length === 0 ? (
            <div className="text-sm text-slate-500 italic p-4 text-center">No cases found. Run demo_m35.py to populate.</div>
          ) : (
            cases.map((c) => (
              <button
                key={c.case_id}
                onClick={() => setSelectedCase(c.case_id)}
                className={`w-full text-left p-4 rounded-xl transition-all duration-300 ${
                  selectedCase === c.case_id 
                    ? 'bg-blue-500/20 border border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]' 
                    : 'glass-card'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-semibold text-slate-200">{c.case_id}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full uppercase font-bold tracking-wide ${
                    c.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                    c.status === 'quarantined' ? 'bg-rose-500/20 text-rose-400' :
                    'bg-amber-500/20 text-amber-400'
                  }`}>
                    {c.status}
                  </span>
                </div>
                <div className="text-xs text-slate-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {new Date(c.created_at).toLocaleTimeString()}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative z-10">
        
        {/* Scientific Banner */}
        <div className="bg-amber-500/10 border-b border-amber-500/20 p-3 flex items-center justify-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          <span className="text-xs font-bold text-amber-500 uppercase tracking-widest">
            {caseDetails?.scientific_status || "EXPERIMENTAL / UNVALIDATED"}
          </span>
        </div>

        {selectedCase ? (
          <div className="flex-1 overflow-y-auto p-8 relative">
            
            {/* Background decorative blob */}
            <div className="absolute top-20 right-20 w-96 h-96 bg-blue-600/10 rounded-full blur-[100px] pointer-events-none animate-float" />
            <div className="absolute bottom-20 left-20 w-80 h-80 bg-indigo-600/10 rounded-full blur-[100px] pointer-events-none animate-float" style={{animationDelay: '3s'}} />

            {loading ? (
              <div className="flex items-center justify-center h-full">
                <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : caseDetails ? (
              <div className="max-w-5xl mx-auto space-y-8 relative z-10">
                
                {/* Header */}
                <div className="flex justify-between items-end pb-6 border-b border-slate-800">
                  <div>
                    <h2 className="text-3xl font-bold text-white mb-2">{caseDetails.case_id}</h2>
                    <p className="text-slate-400 text-sm">Created {new Date(caseDetails.created_at).toLocaleString()}</p>
                  </div>
                  <div className={`px-4 py-1.5 rounded-full border text-sm font-bold tracking-wide uppercase shadow-lg ${
                    caseDetails.status === 'completed' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' :
                    caseDetails.status === 'quarantined' ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' :
                    'bg-blue-500/10 border-blue-500/30 text-blue-400'
                  }`}>
                    {caseDetails.status}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-6">
                  
                  {/* Status Badges */}
                  <div className="col-span-3 grid grid-cols-3 gap-6">
                    <div className="glass-panel p-6 rounded-2xl">
                      <div className="flex items-center gap-3 mb-4">
                        <Activity className="w-5 h-5 text-blue-400" />
                        <h3 className="font-semibold text-slate-300">Events</h3>
                      </div>
                      <div className="text-3xl font-bold text-white">{caseDetails.n_events}</div>
                    </div>
                    <div className="glass-panel p-6 rounded-2xl">
                      <div className="flex items-center gap-3 mb-4">
                        <FileText className="w-5 h-5 text-indigo-400" />
                        <h3 className="font-semibold text-slate-300">Artifacts</h3>
                      </div>
                      <div className="text-3xl font-bold text-white">{caseDetails.n_artifacts}</div>
                    </div>
                    <div className="glass-panel p-6 rounded-2xl">
                      <div className="flex items-center gap-3 mb-4">
                        <ShieldAlert className="w-5 h-5 text-amber-400" />
                        <h3 className="font-semibold text-slate-300">Validation</h3>
                      </div>
                      <div className="text-sm font-medium text-amber-500 uppercase">M2.2 Deferred</div>
                    </div>
                  </div>

                  {/* Artifacts List */}
                  <div className="col-span-1 glass-panel rounded-2xl p-6 h-[500px] flex flex-col">
                    <h3 className="font-semibold text-slate-200 mb-6 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-400" /> 
                      Artifact Registry
                    </h3>
                    <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                      {artifacts.map(a => (
                        <div key={a.id} className="glass-card p-3 rounded-lg border-l-2 border-l-indigo-500">
                          <div className="text-xs font-bold text-indigo-400 mb-1 uppercase">{a.type}</div>
                          <div className="text-[10px] text-slate-400 font-mono truncate" title={a.id}>{a.id}</div>
                          <div className="text-[10px] text-slate-500 mt-2">by {a.produced_by}</div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Event Timeline */}
                  <div className="col-span-2 glass-panel rounded-2xl p-6 h-[500px] flex flex-col">
                    <h3 className="font-semibold text-slate-200 mb-6 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-slate-400" />
                      Immutable Event Log
                    </h3>
                    <div className="flex-1 overflow-y-auto pr-2 relative">
                      <div className="absolute top-0 bottom-0 left-[11px] w-0.5 bg-slate-800" />
                      <div className="space-y-6 relative">
                        {events.map((e) => (
                          <div key={e.event_id} className="flex gap-4 group">
                            <div className="relative mt-1">
                              <div className="w-6 h-6 rounded-full bg-slate-900 border-2 border-blue-500/50 flex items-center justify-center z-10 relative group-hover:border-blue-400 transition-colors">
                                <div className="w-2 h-2 rounded-full bg-blue-500 group-hover:bg-blue-400 transition-colors" />
                              </div>
                            </div>
                            <div className="flex-1 glass p-4 rounded-xl border border-slate-700/50 group-hover:border-slate-600 transition-colors">
                              <div className="flex justify-between items-start mb-1">
                                <span className="font-mono text-sm font-bold text-slate-200">{e.event_type}</span>
                                <span className="text-xs text-slate-500">{new Date(e.timestamp).toLocaleTimeString()}</span>
                              </div>
                              <div className="text-[10px] text-slate-400 font-mono truncate mt-2">ID: {e.event_id} | Actor: {e.actor}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-4">
            <Anchor className="w-16 h-16 opacity-20" />
            <p className="text-lg">Select a case from the sidebar to view details</p>
          </div>
        )}
      </div>
    </div>
  );
}
