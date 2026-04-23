import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAppStore } from './store/appStore';
import Sidebar from './components/shared/Sidebar';
import PredictionPage from './pages/PredictionPage';
import DashboardPage from './pages/DashboardPage';
import PoisonLogPage from './pages/PoisonLogPage';
import AdminPage from './pages/AdminPage';

function App() {
  const { poisonFlashActive, triggerPoisonFlash } = useAppStore();

  return (
    <BrowserRouter>
      <div className={`h-screen w-screen flex bg-bg overflow-hidden ${poisonFlashActive ? 'poison-flash' : ''}`}>
        {/* Sidebar */}
        <Sidebar />

        {/* Main content */}
        <main className="ml-[60px] flex-1 h-screen overflow-hidden">
          <Routes>
            <Route path="/" element={<PredictionPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/poison" element={<PoisonLogPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>

        {/* Simulate Poison Event button */}
        <button
          onClick={triggerPoisonFlash}
          className="fixed bottom-4 right-4 z-50 px-3 py-1.5 bg-bg-panel border border-accent-danger/30 text-accent-danger font-mono text-[10px] hover:bg-accent-danger/10 hover:border-accent-danger transition-colors"
        >
          SIMULATE POISON EVENT
        </button>
      </div>
    </BrowserRouter>
  );
}

export default App;
