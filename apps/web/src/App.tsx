import { BrowserRouter, Route, Routes } from "react-router-dom";
import { DecisionDbPage } from "./pages/DecisionDbPage";
import { EvidencePage } from "./pages/EvidencePage";
import { KnowledgeHome } from "./pages/KnowledgeHome";
import { PolicyDbPage } from "./pages/PolicyDbPage";

export function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Routes>
          <Route path="/" element={<KnowledgeHome />} />
          <Route path="/policies" element={<PolicyDbPage />} />
          <Route path="/decisions" element={<DecisionDbPage />} />
          <Route path="/evidence/:kind/:targetId" element={<EvidencePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
