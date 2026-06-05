function eps = cole_cole(f, eps_inf, delta_eps, tau, alpha, sigma_dc)
%COLE_COLE  Complex relative permittivity of a Cole-Cole + DC-conductivity model.
%
%   eps = COLE_COLE(f, eps_inf, delta_eps, tau, alpha, sigma_dc)
%
%   Reference MATLAB/Octave port of the Python `dielectric` core evaluator, for the research
%   group's existing MATLAB workflows. Sign convention is engineering e^{j w t}:
%
%       eps* = eps_inf + delta_eps / (1 + (j w tau)^(1-alpha)) - j sigma_dc / (w eps0)
%
%   so Im(eps*) < 0 for a lossy medium (eps'' = -Im(eps*) is the conventional positive loss).
%
%   Inputs
%     f         frequency vector [Hz]
%     eps_inf   high-frequency permittivity
%     delta_eps relaxation strength (eps_s - eps_inf)
%     tau       relaxation time [s]
%     alpha     Cole-Cole broadening in [0,1)  (alpha = 0 -> Debye)
%     sigma_dc  DC ionic conductivity [S/m]    (default 0)
%
%   Output
%     eps       complex relative permittivity, internal convention (Im < 0)

  if nargin < 6 || isempty(sigma_dc)
    sigma_dc = 0;
  end
  eps0  = 8.8541878128e-12;          % vacuum permittivity [F/m]
  w     = 2 * pi * f(:);             % angular frequency, column vector
  relax = delta_eps ./ (1 + (1i * w * tau).^(1 - alpha));
  cond  = -1i * sigma_dc ./ (w * eps0);
  eps   = eps_inf + relax + cond;
end
