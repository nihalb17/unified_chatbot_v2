import React, { useState } from 'react';
import {
  Search,
  ShieldCheck,
  Zap,
  BarChart2,
  ArrowRight,
  Sun,
  Moon,
  TrendingUp,
  PieChart,
  Activity,
  Globe,
  DollarSign,
  Landmark,
  Users,
  Percent,
  Star,
  ArrowUpRight,
  ExternalLink
} from 'lucide-react';
import Chatbot from './components/Chatbot';
import './index.css';

const marketData = [
  { name: 'NIFTY 50', value: '24,712.30', change: '+0.84%', positive: true },
  { name: 'SENSEX', value: '81,224.10', change: '+0.62%', positive: true },
  { name: 'BANK NIFTY', value: '52,108.55', change: '-0.21%', positive: false },
  { name: 'RELIANCE', value: '2,945.50', change: '+1.12%', positive: true },
  { name: 'TCS', value: '4,180.25', change: '+0.45%', positive: true },
  { name: 'HDFC BANK', value: '1,685.00', change: '-0.33%', positive: false },
  { name: 'INFY', value: '1,920.75', change: '+0.78%', positive: true },
  { name: 'ITC', value: '425.30', change: '+0.55%', positive: true },
];

const statsData = [
  { value: '5Cr+', label: 'Happy investors' },
  { value: '₹4L Cr+', label: 'Assets managed' },
  { value: '0%', label: 'Brokerage on delivery' },
  { value: '4.5★', label: 'Play Store rating' },
];

const productsData = [
  {
    icon: TrendingUp,
    title: 'Stocks',
    desc: 'Invest in 5000+ NSE & BSE stocks with zero brokerage on delivery.',
  },
  {
    icon: PieChart,
    title: 'Mutual Funds',
    desc: 'Direct mutual funds with 0% commission. Earn up to 1.5% extra returns.',
  },
  {
    icon: Activity,
    title: 'Futures & Options',
    desc: 'Trade F&O with the lowest brokerage and lightning-fast execution.',
  },
  {
    icon: Globe,
    title: 'US Stocks',
    desc: 'Own a piece of Apple, Tesla, Google. Invest from as little as $1.',
  },
  {
    icon: DollarSign,
    title: 'Digital Gold',
    desc: 'Buy 24K pure digital gold starting at just ₹10. Sell anytime.',
  },
  {
    icon: Landmark,
    title: 'Fixed Deposits',
    desc: 'Earn up to 9.5% with FDs from top banks. 100% secure & insured.',
  },
];

const footerLinks = {
  products: [
    { label: 'Stocks', href: '#' },
    { label: 'Mutual Funds', href: '#' },
    { label: 'F&O', href: '#' },
    { label: 'US Stocks', href: '#' },
    { label: 'FDs', href: '#' },
  ],
  company: [
    { label: 'About', href: '#' },
    { label: 'Careers', href: '#' },
    { label: 'Press', href: '#' },
    { label: 'Contact', href: '#' },
    { label: 'Help', href: '#' },
  ],
  legal: [
    { label: 'Terms', href: '#' },
    { label: 'Privacy', href: '#' },
    { label: 'Disclosure', href: '#' },
    { label: 'SEBI', href: '#' },
    { label: 'Grievance', href: '#' },
  ],
};

function App() {
  const [isDark, setIsDark] = useState(true);

  const toggleTheme = () => {
    setIsDark(!isDark);
  };

  return (
    <div className={`app-container ${!isDark ? 'light' : ''}`}>
      {/* Navbar */}
      <nav className="navbar">
        <div className="nav-left">
          <div className="logo">
            <div className="logo-icon">
              <Zap size={20} />
            </div>
            Groww
          </div>
          <div className="nav-links">
            <a href="#" className="active">Stocks</a>
            <a href="#">Mutual Funds</a>
            <a href="#">F&O</a>
            <a href="#">US Stocks</a>
            <a href="#">Bonds</a>
          </div>
        </div>

        <div className="nav-right">
          <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button className="btn-login">Login</button>
          <button className="btn-signup">Sign Up</button>
        </div>
      </nav>

      {/* Market Ticker */}
      <div className="market-ticker">
        <div className="ticker-track">
          {[...marketData, ...marketData].map((item, idx) => (
            <span key={idx} className="ticker-item">
              <span className="ticker-name">{item.name}</span>
              <span className="ticker-value">{item.value}</span>
              <span className={`ticker-change ${item.positive ? 'positive' : 'negative'}`}>
                {item.change}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <main className="main-content">
        {/* Hero Section */}
        <section className="hero-section">
          <div className="hero-inner">
            {/* Left Text */}
            <div className="hero-text">
              <div className="tagline">
                <span className="tagline-dot"></span>
                India's #1 investment platform · 5Cr+ users
              </div>

              <h1 className="hero-title">
                Invest in <br />
                <span className="highlight">everything.</span><br />
                Grow your wealth.
              </h1>

              <p className="hero-subtitle">
                Stocks, Mutual Funds, F&O, IPOs, US Stocks & more — all in one zero-commission app trusted by millions.
              </p>

              <div className="cta-group">
                <button className="btn-primary">
                  Start Investing <ArrowRight size={18} />
                </button>
                <button className="btn-secondary">
                  Explore Mutual Funds
                </button>
              </div>

              <div className="features-list">
                <div className="feature-item">
                  <ShieldCheck size={16} /> SEBI registered
                </div>
                <div className="feature-item">
                  <Zap size={16} /> Instant withdrawals
                </div>
                <div className="feature-item">
                  <BarChart2 size={16} /> Zero commission
                </div>
              </div>
            </div>

            {/* Right Visual */}
            <div className="hero-visual">
              <div className="portfolio-card">
                <div className="card-header">
                  <div className="card-subtitle">Portfolio value</div>
                  <div className="card-value-row">
                    <div className="card-value">₹ 4,82,165.20</div>
                    <div className="badge">+12.4%</div>
                  </div>
                </div>

                <div className="chart-area">
                  <div className="chart-line"></div>
                </div>

                <div className="stats-grid">
                  <div className="stat-box">
                    <div className="stat-title">Stocks</div>
                    <div className="stat-value">₹ 2.1L</div>
                    <div className="stat-change positive">+8.2%</div>
                  </div>
                  <div className="stat-box active">
                    <div className="stat-title">MF</div>
                    <div className="stat-value">₹ 1.8L</div>
                    <div className="stat-change positive">+14.7%</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-title">Gold</div>
                    <div className="stat-value">₹ 92K</div>
                    <div className="stat-change positive">+5.1%</div>
                  </div>
                </div>

                <div className="today-gain">
                  <span className="today-gain-label">Today's gain</span>
                  <span className="today-gain-value">+₹4,218.55</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        <section className="stats-section">
          <div className="stats-row">
            {statsData.map((stat, idx) => (
              <div key={idx} className="stat-item">
                <div className="stat-item-value">{stat.value}</div>
                <div className="stat-item-label">{stat.label}</div>
              </div>
            ))}
          </div>
        </section>

        {/* Products Section */}
        <section className="products-section">
          <div className="section-header">
            <h2 className="section-title">One app. Every investment.</h2>
            <p className="section-subtitle">
              From stocks to gold — invest across asset classes from one simple app.
            </p>
          </div>
          <div className="products-grid">
            {productsData.map((product, idx) => {
              const Icon = product.icon;
              return (
                <div key={idx} className="product-card">
                  <div className="product-icon">
                    <Icon size={20} />
                  </div>
                  <div className="product-title">{product.title}</div>
                  <div className="product-desc">{product.desc}</div>
                </div>
              );
            })}
          </div>
        </section>

        {/* CTA Section */}
        <section className="cta-section">
          <div className="cta-inner">
            <h2 className="cta-title">Ready to grow your wealth?</h2>
            <p className="cta-subtitle">
              Open a free account in under 2 minutes.
            </p>
            <button className="btn-cta">
              Get Started Free <ArrowUpRight size={18} />
            </button>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-inner">
          <div className="footer-grid">
            <div>
              <div className="footer-brand">
                <div className="footer-brand-icon">
                  <Zap size={16} />
                </div>
                Groww
              </div>
              <p className="footer-tagline">
                India's most loved investment platform. Trusted by 5Cr+ investors for a reason.
              </p>
            </div>
            <div className="footer-column">
              <h4>Products</h4>
              <ul>
                {footerLinks.products.map((link, idx) => (
                  <li key={idx}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
            <div className="footer-column">
              <h4>Company</h4>
              <ul>
                {footerLinks.company.map((link, idx) => (
                  <li key={idx}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
            <div className="footer-column">
              <h4>Legal</h4>
              <ul>
                {footerLinks.legal.map((link, idx) => (
                  <li key={idx}>
                    <a href={link.href}>{link.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="footer-bottom">
            <div className="footer-copyright">
              © 2026 Groww. All rights reserved.
            </div>
            <div className="footer-social">
              <a href="#" aria-label="Social">
                <ExternalLink size={18} />
              </a>
              <a href="#" aria-label="Social">
                <ExternalLink size={18} />
              </a>
              <a href="#" aria-label="Social">
                <ExternalLink size={18} />
              </a>
            </div>
          </div>
        </div>
      </footer>

      {/* Floating Chatbot */}
      <Chatbot isDark={isDark} />
    </div>
  );
}

export default App;
