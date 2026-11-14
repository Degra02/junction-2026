const DEFAULT_ENDPOINT = "https://the4thlover.tech";

const MENU_IDS = {
  selection: "dtn-check-selection",
  link: "dtn-check-link",
  page: "dtn-check-page",
};

function installContextMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_IDS.selection,
      title: "Check selected text with Decode the Noise",
      contexts: ["selection"],
    });
    chrome.contextMenus.create({
      id: MENU_IDS.link,
      title: "Check link coverage with Decode the Noise",
      contexts: ["link"],
    });
    chrome.contextMenus.create({
      id: MENU_IDS.page,
      title: "Check this page with Decode the Noise",
      contexts: ["page"],
    });
  });
}

chrome.runtime.onInstalled.addListener(() => {
  installContextMenus();
});

async function getEndpoint() {
  const stored = await chrome.storage.local.get(["endpoint"]);
  const raw = typeof stored.endpoint === "string" && stored.endpoint.trim()
    ? stored.endpoint.trim()
    : DEFAULT_ENDPOINT;
  return raw.replace(/\/+$/, "");
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const endpoint = await getEndpoint();
  const params = new URLSearchParams();

  if (info.menuItemId === MENU_IDS.selection && info.selectionText) {
    params.set("text", info.selectionText.trim().slice(0, 12000));
    params.set("autorun", "1");
  } else if (info.menuItemId === MENU_IDS.link && info.linkUrl) {
    params.set("url", info.linkUrl);
    params.set("autorun", "1");
  } else {
    const pageUrl = info.pageUrl || (tab && tab.url) || "";
    if (!/^https?:\/\//i.test(pageUrl)) return;
    params.set("url", pageUrl);
    params.set("autorun", "1");
  }

  await chrome.tabs.create({ url: `${endpoint}/?${params.toString()}` });
});
