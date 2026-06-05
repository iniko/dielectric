function [params, gof] = fit_cole_cole(f, eps_meas)
%FIT_COLE_COLE  Fit a Cole-Cole + DC-conductivity model to measured complex permittivity.
%
%   [params, gof] = FIT_COLE_COLE(f, eps_meas)
%
%   Non-linear least squares on the stacked real/imaginary residuals. The relaxation time tau is
%   optimised in LOG10 space (multi-decade parameter; a linear step makes the Jacobian column for
%   tau useless and the fit diverges) — matching the Python reference engine.
%
%   Inputs
%     f         frequency vector [Hz]
%     eps_meas  measured complex permittivity, internal convention (Im < 0). If your data stores
%               positive loss, pass eps' - 1i*eps'' .
%
%   Outputs
%     params  struct with fields eps_inf, delta_eps, tau, alpha, sigma_dc
%     gof     struct with fields rss, r2

  f = f(:); eps_meas = eps_meas(:);
  eps0 = 8.8541878128e-12;
  w = 2*pi*f;

  % Data-driven initial guess (mirrors the Python fitters).
  eps_inf0 = max(real(eps_meas(end)), 1);
  eps_s0   = real(eps_meas(1));
  loss0    = -imag(eps_meas);
  sigma0   = max(loss0(1) * w(1) * eps0, 0);
  delta0   = max(eps_s0 - eps_inf0, 1);
  tau0     = 1/(2*pi*f(end));            % water-like relaxation near the band edge

  % Optimise [eps_inf, delta_eps, log10(tau), alpha, sigma_dc].
  p0 = [eps_inf0, delta0, log10(tau0), 0.1, sigma0];

  function r = resid(p)
    e = cole_cole(f, p(1), p(2), 10.^p(3), p(4), p(5));
    r = [real(e - eps_meas); imag(e - eps_meas)];
  end

  opts = optimset('Display', 'off', 'MaxFunEvals', 20000, 'MaxIter', 5000);
  if exist('lsqnonlin', 'file')
    lb = [1,    0,   -14, 0,    0];
    ub = [1e3,  1e7, -6,  0.99, 1e3];
    phat = lsqnonlin(@resid, p0, lb, ub, opts);
  else
    phat = fminsearch(@(p) sum(resid(p).^2), p0, opts);
  end

  params = struct('eps_inf', phat(1), 'delta_eps', phat(2), 'tau', 10.^phat(3), ...
                  'alpha', phat(4), 'sigma_dc', phat(5));

  e = cole_cole(f, params.eps_inf, params.delta_eps, params.tau, params.alpha, params.sigma_dc);
  stacked_meas = [real(eps_meas); imag(eps_meas)];
  rss = sum((stacked_meas - [real(e); imag(e)]).^2);
  ss_tot = sum((stacked_meas - mean(stacked_meas)).^2);
  gof = struct('rss', rss, 'r2', 1 - rss/ss_tot);
end
