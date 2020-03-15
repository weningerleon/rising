import torch
from random import shuffle
from typing import Sequence, Union, Callable, Any, Mapping


from rising.utils import check_scalar
from rising.transforms import AbstractTransform, RandomProcess


__all__ = ["Compose", "DropoutCompose"]


def dict_call(batch: dict, transform: Callable) -> Any:
    """
    Unpacks the dict for every transformation

    Parameters
    ----------
    batch: dict
        current batch which is passed to transform
    transform: Callable
        transform to perform

    Returns
    -------
    Any
        transformed batch
    """
    return transform(**batch)


class _TransformWrapper(torch.nn.Module):
    def __init__(self, trafo: Callable):
        """
        Helper Class to wrap all non-module transforms into modules to use the
        torch.nn.ModuleList as container for the transforms. This enables
        forwarding of all model specific calls as ``.to()`` to all transforms

        Parameters
        ----------
        trafo : Callable
            the actual transform, which will be wrapped by this class.
            Since this transform is no subclass of ``torch.nn.Module``,
            its internal state won't be affected by module specific calls
        """
        super().__init__()

        self.trafo = trafo

    def forward(self, *args, **kwargs) -> Any:
        """
        Forwards calls to this wrapper to the internal transform
        """
        return self.trafo(*args, **kwargs)


class Compose(AbstractTransform):
    def __init__(self, *transforms, shuffle: bool = False,
                 transform_call: Callable[[Any, Callable], Any] = dict_call):
        """
        Compose multiple transforms

        Parameters
        ----------
        transforms: Union[AbstractTransform, Sequence[AbstractTransform]]
            one or multiple transformations which are applied in consecutive
            order
        shuffle: bool
            aplly transforms in random order
        transform_call: Callable[[Any, Callable], Any], optional
            function which determines how transforms are called. By default
            Mappings and Sequences are unpacked during the transform.
        """
        super().__init__(grad=True)
        if isinstance(transforms[0], Sequence):
            transforms = transforms[0]

        self.transforms = transforms
        self.transform_call = transform_call
        self.shuffle = shuffle

    def forward(self, *seq_like, **map_like) -> Union[Sequence, Mapping]:
        """
        Apply transforms in a consecutive order. Can either handle
        Sequence like or Mapping like data.

        Parameters
        ----------
        seq_like: tuple
            data which is unpacked like a Sequence
        map_like: dict
            data which is unpacked like a dict

        Returns
        -------
        dict
            dict with transformed data
        """
        assert not (seq_like and map_like)
        assert len(self.transforms) == len(self.transform_order)
        data = seq_like if seq_like else map_like

        if self.shuffle:
            shuffle(self.transform_order)

        for idx in self.transform_order:
            data = self.transform_call(data, self.transforms[idx])
        return data

    @property
    def transforms(self) -> torch.nn.ModuleList:
        """
        Transforms getter

        Returns
        -------
        torch.nn.ModuleList
            transforms to compose
        """
        return self._transforms

    @transforms.setter
    def transforms(self, transforms: Union[AbstractTransform,
                                           Sequence[AbstractTransform]]):
        """
        Transforms setter

        Parameters
        ----------
        transforms: Union[AbstractTransform, Sequence[AbstractTransform]]
            one or multiple transformations which are applied in consecutive
            order

        Returns
        -------
        torch.nn.ModuleList
            transforms to compose
        """
        # make transforms a list to be mutable.
        # Otherwise the enforced typesetting below might fail.
        if isinstance(transforms, tuple):
            transforms = list(transforms)

        for idx, trafo in enumerate(transforms):
            if not isinstance(trafo, torch.nn.Module):
                transforms[idx] = _TransformWrapper(trafo)

        self._transforms = torch.nn.ModuleList(transforms)
        self.transform_order = list(range(len(self.transforms)))

    @property
    def shuffle(self) -> bool:
        """
        Getter for attribute shuffle

        Returns
        -------
        bool
            True if shuffle is enabled, False otherwise
        """
        return self._shuffle

    @shuffle.setter
    def shuffle(self, shuffle: bool):
        """
        Setter for shuffle

        Parameters
        ----------
        shuffle : bool
            new status of shuffle
        """
        self._shuffle = shuffle
        self.transform_order = list(range(len(self.transforms)))


class DropoutCompose(RandomProcess, Compose):
    def __init__(self, *transforms, dropout: Union[float, Sequence[float]] = 0.5,
                 random_mode: str = "random", random_args: Sequence = (), random_module: str = "random",
                 transform_call: Callable[[Any, Callable], Any] = dict_call,
                 **kwargs):
        """
        Compose multiple transforms to one

        Parameters
        ----------
        transforms: Union[AbstractTransform, Sequence[AbstractTransform]]
            one or multiple transformations which are applied in consecutive order
        dropout: Union[float, Sequence[float]]
            if provided as float, each transform is skipped with the given probability
            if :param:`dropout` is a sequence, it needs to specify the dropout
            probability for each given transform
        random_mode: str
            specifies distribution which should be used to sample additive value
        random_args: Sequence
            positional arguments passed for random function
        random_module: str
            module from where function random function should be imported
        transform_call: Callable[[Any, Callable], Any], optional
            function which determines how transforms are called. By default
            Mappings and Sequences are unpacked during the transform.

        Raises
        ------
        TypeError
            if dropout is a sequence it must have the same length as transforms
        """
        super().__init__(*transforms, random_mode=random_mode,
                         random_args=random_args, random_module=random_module,
                         rand_seq=False, transform_call=transform_call, **kwargs)
        if check_scalar(dropout):
            dropout = [dropout] * len(self.transforms)
        if len(dropout) != len(self.transforms):
            raise TypeError(f"If dropout is a sequence it must specify the dropout probability "
                            f"for each transform, found {len(dropout)} probabilities "
                            f"and {len(self.transforms)} transforms.")
        self.dropout = dropout

    def forward(self, *seq_like, **map_like) -> Union[Sequence, Mapping]:
        """
        Apply transforms in a consecutive order. Can either handle
        Sequence like or Mapping like data.

        Parameters
        ----------
        seq_like: tuple
            data which is unpacked like a Sequence
        map_like: dict
            data which is unpacked like a dict

        Returns
        -------
        dict
            dict with transformed data
        """
        assert not (seq_like and map_like)
        assert len(self.transforms) == len(self.transform_order)
        data = seq_like if seq_like else map_like

        for idx in self.transform_order:
            if self.rand() > self.dropout[idx]:
                data = self.transform_call(data, self.transforms[idx])
        return data
