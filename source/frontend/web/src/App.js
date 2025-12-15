import React, { Component, createRef } from "react";
import { withAuthenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { Icon, Link, Modal, Box, SpaceBetween, Checkbox } from "@cloudscape-design/components";
import FrameVideoMain from "./components/frameSample/videoMain";
import ClipVideoMain from "./components/videoClip/videoMain";
import NovaMmeVideoMain from "./components/novaMme/videoMain";
import TlabsMmeVideoMain from "./components/tlabsMme/videoMain";
import AgentMain from "./components/agent/agentMain";
import DataGenerationMain from "./components/dataGeneration/dataMain";
import "./App.css";
import { FetchPost } from "./resources/data-provider";
import mainLogo from "./static/aws-logo.svg";
import bedrockLogo from "./static/bedrock_logo.png";

const ITEMS = [
  { type: "link", text: "Frame Based", id: "frame", href: "#/frame" },
  { type: "link", text: "Shot Based", id: "clip", href: "#/clip" },
  { type: "link", text: "Nova MME", id: "novamme", href: "#/novamme" },
  { type: "link", text: "TwelveLabs", id: "tlabsmme", href: "#/tlabsmme" },
  { type: "link", text: "Data Generation", id: "datagen", href: "#/datagen" },
  { type: "link", text: "Chat with an agent", id: "agent", href: "#/agent" },
];

class App extends Component {
  constructor(props) {
    super(props);

    const envMenus = process.env.REACT_APP_READONLY_DISPLAY_MENUS
      ? process.env.REACT_APP_READONLY_DISPLAY_MENUS.split(",")
      : [];
    
    const initialVisibleMenus = envMenus.length > 0 
      ? envMenus 
      : ITEMS.map(item => item.id);

    this.state = {
      currentPage: "frame",
      navigationOpen: true,
      activeNavHref: "#/frame",
      displayTopMenu: window.self === window.top,
      cleanSelectionSignal: null,
      smUrl: null,
      showSettingsModal: false,
      visibleMenus: initialVisibleMenus,
    };

    this.appLayout = createRef();
    this.getReadOnlyUsers = this.getReadOnlyUsers.bind(this);
    this.handleMenuClick = this.handleMenuClick.bind(this);
    this.handleAnalyzeVideos = this.handleAnalyzeVideos.bind(this);
    this.handleSettingsClick = this.handleSettingsClick.bind(this);
    this.handleMenuToggle = this.handleMenuToggle.bind(this);
    this.closeSettingsModal = this.closeSettingsModal.bind(this);
  }

  componentDidMount() {
    this.fetchSmUrl();
  }

  async fetchSmUrl() {
    try {
      const data = await FetchPost("/extraction/video/get-sm-url", {}, "ExtrService");
      const resp = data.body;
      if (data.statusCode !== 200) {
        this.setState({ smUrl: "" });
        return "";
      } else {
        const url = resp ? resp : "";
        this.setState({ smUrl: url });
        return url;
      }
    } catch (err) {
      this.setState({ smUrl: "" });
      return "";
    }
  }

  async handleAnalyzeVideos() {
    const url = await this.fetchSmUrl();
    if (url && url.length > 0) {
      window.open(url, "_blank");
    } else {
      alert("Unable to retrieve the Studio URL. Please try again later.");
    }
  }

  getReadOnlyUsers() {
    if (process.env.REACT_APP_READONLY_USERS)
      return process.env.REACT_APP_READONLY_USERS.toString().split(",");
    else return [];
  }

  handleMenuClick(id) {
    this.setState({
      currentPage: id,
      cleanSelectionSignal: Math.random(),
    });
  }

  handleSettingsClick() {
    this.setState({ showSettingsModal: true });
  }

  closeSettingsModal() {
    this.setState({ showSettingsModal: false });
  }

  handleMenuToggle(menuId) {
    this.setState(prevState => {
      const visibleMenus = prevState.visibleMenus.includes(menuId)
        ? prevState.visibleMenus.filter(id => id !== menuId)
        : [...prevState.visibleMenus, menuId];
      
      return { visibleMenus };
    });
  }

  render() {
    const { signOut, user } = this.props;
    const { currentPage, displayTopMenu, smUrl, cleanSelectionSignal, showSettingsModal, visibleMenus } = this.state;

    return (
      <div className="app">
        {displayTopMenu && (
          <div className="topmenu">
            <div className="header-left">
              <img src={mainLogo} alt="Main" className="logo main-logo" />
              <div className="title"><strong>Bedrock Video Understanding</strong></div>
            </div>
            <div className="header-right">
              <img src={bedrockLogo} alt="Amazon Bedrock" className="logo bedrock-logo" />
              <div className="user" title={user.email}>
                <Icon name="user-profile-active"></Icon>&nbsp;&nbsp;
                {user.username}
              </div>
            </div>
          </div>
        )}

        <div className="sidemenu">
          {ITEMS.map((item, index) =>
            visibleMenus.includes(item.id) ? (
              <div
                key={`menu_${index}`}
                className={item.id === currentPage ? "itemselected" : "item"}
                onClick={() => this.handleMenuClick(item.id)}
              >
                {item.text}
              </div>
            ) : null
          )}

          <div className="bottom">
            <div className="item" onClick={this.handleAnalyzeVideos}>
              <Link variant="primary">Analyze Videos</Link>
              <br />
            </div>
            <div className="item" onClick={() => signOut()}>
              Logout
            </div>
            {process.env.REACT_APP_SHOW_SETTINGS_ICON === "true" && (
              <div className="item settings-icon" onClick={this.handleSettingsClick}>
                <Icon name="settings" size="medium" />
              </div>
            )}
          </div>
        </div>

        <Modal
          visible={showSettingsModal}
          onDismiss={this.closeSettingsModal}
          header="Menu Settings"
          footer={
            <Box float="right">
              <Link variant="primary" onClick={this.closeSettingsModal}>
                Close
              </Link>
            </Box>
          }
        >
          <SpaceBetween size="m">
            <Box>Select which menus to display:</Box>
            {ITEMS.map((item) => (
              <Checkbox
                key={item.id}
                checked={visibleMenus.includes(item.id)}
                onChange={() => this.handleMenuToggle(item.id)}
              >
                {item.text}
              </Checkbox>
            ))}
          </SpaceBetween>
        </Modal>

        <div className="content">
          {currentPage === "frame" ? (
            <FrameVideoMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "clip" ? (
            <ClipVideoMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "novamme" ? (
            <NovaMmeVideoMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "tlabsmme" ? (
            <TlabsMmeVideoMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "datagen" ? (
            <DataGenerationMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "agent" ? (
            <AgentMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : (
            <div />
          )}
        </div>
      </div>
    );
  }
}

export default withAuthenticator(App);
