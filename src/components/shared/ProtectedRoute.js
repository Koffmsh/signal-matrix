import { Navigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

const ProtectedRoute = ({ children, requireAdmin = false }) => {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return (
      <div style={{ padding: "40px", color: "#8899aa", textAlign: "center", fontFamily: "'IBM Plex Mono', 'Courier New', monospace" }}>
        Loading...
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (requireAdmin && user.role !== "admin") return <Navigate to="/" replace />;

  return children;
};

export default ProtectedRoute;
