import { Component } from "react";
import EmptyState from "./EmptyState.jsx";

/**
 * Filet de sécurité React. Sans lui, une carte malformée (un champ absent
 * côté brain, une intégration qui renvoie null) fait planter tout l'arbre
 * au premier rendu — écran noir, plus de navigation, plus de moyen de
 * revenir. Deux usages : une boundary large autour de chaque <Screen />
 * (App.jsx) et une plus fine autour de chaque carte (CardView.jsx), pour
 * qu'une tuile cassée ne coûte que sa propre tuile.
 */
export default class ErrorBoundary extends Component {
  state = { broken: false };

  static getDerivedStateFromError() {
    return { broken: true };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", this.props.label || "", error, info);
  }

  reset = () => this.setState({ broken: false });

  render() {
    if (!this.state.broken) return this.props.children;
    if (this.props.compact) {
      return (
        <div className="card-broken">
          <span className="card-row-sub">Cette carte a rencontré un problème.</span>
        </div>
      );
    }
    return (
      <EmptyState
        icon="alert"
        title="Cet écran a rencontré un problème"
        text="Un rechargement suffit en général à repartir sur une base saine."
        action={
          <button type="button" className="btn btn--primary" onClick={() => window.location.reload()}>
            Recharger
          </button>
        }
      />
    );
  }
}
