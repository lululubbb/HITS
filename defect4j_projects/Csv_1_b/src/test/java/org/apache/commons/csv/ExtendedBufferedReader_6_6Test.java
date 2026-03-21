package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

class ExtendedBufferedReader_6_6Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsNextChar() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        // Use doCallRealMethod() to call real mark/reset methods since they are final in BufferedReader
        doCallRealMethod().when(spyReader).mark(anyInt());
        doReturn((int) 'A').when(spyReader).read();
        doCallRealMethod().when(spyReader).reset();

        int result = spyReader.lookAhead();

        assertEquals('A', result);
        verify(spyReader).mark(anyInt());
        verify(spyReader).read();
        verify(spyReader).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStream() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        doCallRealMethod().when(spyReader).mark(anyInt());
        doReturn(ExtendedBufferedReader.END_OF_STREAM).when(spyReader).read();
        doCallRealMethod().when(spyReader).reset();

        int result = spyReader.lookAhead();

        assertEquals(ExtendedBufferedReader.END_OF_STREAM, result);
        verify(spyReader).mark(anyInt());
        verify(spyReader).read();
        verify(spyReader).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOException() throws Exception {
        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        doThrow(new IOException("mark failed")).when(spyReader).mark(anyInt());

        assertThrows(IOException.class, spyReader::lookAhead);
        verify(spyReader).mark(anyInt());
    }

    @Test
    @Timeout(8000)
    void testLookAheadPrivateViaReflection() throws Exception {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        ExtendedBufferedReader spyReader = Mockito.spy(extendedBufferedReader);

        doCallRealMethod().when(spyReader).mark(anyInt());
        doReturn((int) 'B').when(spyReader).read();
        doCallRealMethod().when(spyReader).reset();

        int result = (int) lookAheadMethod.invoke(spyReader);

        assertEquals('B', result);
    }
}