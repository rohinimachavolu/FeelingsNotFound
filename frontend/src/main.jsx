import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import Survey from "./Survey.jsx";
import Admin from "./Admin.jsx";

const isAdmin = window.location.pathname.replace(/\/+$/, "") === "/admin";
createRoot(document.getElementById("root")).render(
  <React.StrictMode>{isAdmin ? <Admin /> : <Survey />}</React.StrictMode>
);
