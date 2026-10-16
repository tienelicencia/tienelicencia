// GET /api/building?id=<building id from site/data/<area>/buildings.json>
// Every registered tourist flat / establishment in one building (cadastral parcel), from the Junta register.
import { building, search } from "./lib/register-data.mjs";
import { json } from "./lib/http.mjs";

export const config = { path: "/api/building" };

export default async (req) => {
  const id = new URL(req.url).searchParams.get("id") || "";
  if (!/^[A-Za-z0-9]{6,20}$/.test(id)) return json(400, { error: "bad_id" });
  const b = building(id);
  if (!b) return json(404, { error: "not_found" });
  return json(200, { ...b, register_date: search().register_date }, 900);
};
