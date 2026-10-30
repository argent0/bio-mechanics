import raw from "../../../generated/architecture.json";
import { parseArchitecture } from "./load";

/** The single import of `generated/architecture.json`. */
export const ARCHITECTURE = parseArchitecture(raw);
