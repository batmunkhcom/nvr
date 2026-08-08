import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
  // Serialize arrays as repeated keys (?objects=car&objects=person), the
  // format FastAPI list[str] params expect. Default axios emits ?objects[]=...
  // which FastAPI silently ignores (unfiltered results).
  paramsSerializer: { indexes: null },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401 || error.response?.status === 403) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export default apiClient;
