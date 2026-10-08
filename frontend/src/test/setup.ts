import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";
import { afterEach } from "vitest";
import { setAuthToken, setUnauthorizedHandler } from "../api/client";

// findBy*/waitFor default to 1000 ms, too tight when the suite runs in parallel.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  localStorage.clear();
  setAuthToken(null);
  setUnauthorizedHandler(null);
});
