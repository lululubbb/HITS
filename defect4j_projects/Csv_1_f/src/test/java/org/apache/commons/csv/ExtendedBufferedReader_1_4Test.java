package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_1_4Test {

    private Reader mockReader;
    private ExtendedBufferedReader extendedBufferedReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader);
    }

    @Test
    @Timeout(8000)
    void testConstructor() {
        assertNotNull(extendedBufferedReader);
    }

    @Test
    @Timeout(8000)
    void testReadDelegatesToSuper() throws IOException {
        ExtendedBufferedReader spyReader = spy(new ExtendedBufferedReader(mockReader));
        doReturn(42).when(spyReader).read();
        int result = spyReader.read();
        assertEquals(42, result);
    }

    @Test
    @Timeout(8000)
    void testReadAgain() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        ExtendedBufferedReader spyReader = spy(new ExtendedBufferedReader(mockReader));
        doReturn(10).doReturn(ExtendedBufferedReader.END_OF_STREAM).when(spyReader).read();
        Method readAgainMethod = ExtendedBufferedReader.class.getDeclaredMethod("readAgain");
        readAgainMethod.setAccessible(true);
        int firstCall = (int) readAgainMethod.invoke(spyReader);
        int secondCall = (int) readAgainMethod.invoke(spyReader);
        assertEquals(10, firstCall);
        assertEquals(ExtendedBufferedReader.END_OF_STREAM, secondCall);
    }

    @Test
    @Timeout(8000)
    void testReadCharArray() throws IOException {
        char[] buffer = new char[5];
        ExtendedBufferedReader spyReader = spy(new ExtendedBufferedReader(mockReader));
        doReturn(3).when(spyReader).read(buffer, 0, 5);
        int readCount = spyReader.read(buffer, 0, 5);
        assertEquals(3, readCount);
    }

    @Test
    @Timeout(8000)
    void testReadLine() throws IOException {
        ExtendedBufferedReader spyReader = spy(new ExtendedBufferedReader(mockReader));
        doReturn("test line").when(spyReader).readLine();
        String line = spyReader.readLine();
        assertEquals("test line", line);
    }

    @Test
    @Timeout(8000)
    void testLookAhead() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException, IOException {
        ExtendedBufferedReader spyReader = spy(new ExtendedBufferedReader(mockReader));
        doReturn(50).when(spyReader).read();
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);
        int result = (int) lookAheadMethod.invoke(spyReader);
        assertEquals(50, result);
    }

    @Test
    @Timeout(8000)
    void testGetLineNumber() throws NoSuchMethodException, InvocationTargetException, IllegalAccessException {
        Method getLineNumberMethod = ExtendedBufferedReader.class.getDeclaredMethod("getLineNumber");
        getLineNumberMethod.setAccessible(true);
        int lineNumber = (int) getLineNumberMethod.invoke(extendedBufferedReader);
        assertEquals(0, lineNumber);
    }
}