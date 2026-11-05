import { localDev, none, vercelOidc } from "eve/channels/auth";
import { eveChannel } from "eve/channels/eve";

// The app is public, so none() admits anonymous visitors. vercelOidc() still identifies calls
// from this project, such as `eve eval --url`. The limits in agent/agent.ts cap each session.
export default eveChannel({
  auth: [vercelOidc(), localDev(), none()],
  uploadPolicy: "disabled",
});
