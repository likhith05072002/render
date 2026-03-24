import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Part1 from './pages/Part1'
import CallDetail from './pages/CallDetail'
import Part2 from './pages/Part2'
import Part3 from './pages/Part3'
import TestLab from './pages/TestLab'

export default function App() {
  return (
    <div className="app-root">
      <Navbar />
      <div className="page-content">
        <Routes>
          <Route path="/" element={<Part1 />} />
          <Route path="/part1" element={<Part1 />} />
          <Route path="/part1/call/:callId" element={<CallDetail />} />
          <Route path="/part2" element={<Part2 />} />
          <Route path="/part3" element={<Part3 />} />
          <Route path="/test" element={<TestLab />} />
        </Routes>
      </div>
    </div>
  )
}
