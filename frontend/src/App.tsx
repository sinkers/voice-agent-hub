import { BrowserRouter, Route, Routes } from "react-router-dom";
import Call from "./pages/Call";
import Dashboard from "./pages/Dashboard";
import Verify from "./pages/Verify";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/call" element={<Call />} />
        <Route path="/auth/verify" element={<Verify />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
