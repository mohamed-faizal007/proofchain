import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { setAuthToken, setUnauthorizedHandler } from "../api/client";

afterEach(() => {
  localStorage.clear();
  setAuthToken(null);
  setUnauthorizedHandler(null);
});
